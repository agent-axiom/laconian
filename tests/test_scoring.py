import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from laconian_eval import __version__
from laconian_eval.cases import response_case_sha256
from laconian_eval.models import (
    CheckResult,
    ErrorInfo,
    HardConstraints,
    JudgeProvenance,
    RawAttempt,
    ResponseCase,
    ScoredAttempt,
    SemanticRubric,
    TokenUsageModel,
)
from laconian_eval.scoring import (
    count_sentences,
    eligible_for_pairing,
    load_scored_jsonl,
    score_attempt,
    score_terminal_attempts,
    write_scored_jsonl,
)


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def response_case(
    *,
    case_id: str = "scoring-001-en",
    constraints: HardConstraints | None = None,
    rubric: SemanticRubric | None = None,
) -> ResponseCase:
    return ResponseCase(
        id=case_id,
        scenario_id=case_id.removesuffix("-en").removesuffix("-ru"),
        locale="ru" if case_id.endswith("-ru") else "en",
        category="direct",
        prompt=f"Prompt for {case_id}.",
        hard_constraints=constraints or HardConstraints(),
        semantic_rubric=rubric or SemanticRubric(),
    )


def raw_attempt(
    case: ResponseCase,
    *,
    arm: str = "if",
    output: str | None = "Complete.",
    error: ErrorInfo | None = None,
    attempt: int = 1,
    terminal: bool = True,
    run_id: str = "run-1",
    manifest_hash: str | None = None,
    repetition: int = 0,
    usage: TokenUsageModel | None = None,
    prompt_hash: str | None = None,
) -> RawAttempt:
    return RawAttempt(
        runner_version=__version__,
        run_id=run_id,
        manifest_sha256=manifest_hash or digest("manifest-1"),
        case_id=case.id,
        case_definition_sha256=response_case_sha256(case),
        arm=arm,
        repetition=repetition,
        attempt=attempt,
        terminal=terminal,
        retry_of_attempt=attempt - 1 if attempt > 1 else None,
        prompt_sha256=prompt_hash or digest(case.prompt),
        instruction_sha256=digest(f"{arm}-instruction"),
        provider="fake",
        model="fixture-v1",
        started_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        elapsed_ms=7,
        output_text=output,
        usage=usage,
        error=error,
    )


def with_judgment(scored: ScoredAttempt, passed: bool) -> ScoredAttempt:
    return ScoredAttempt.model_validate(
        {
            **scored.model_dump(mode="python"),
            "semantic_pass": passed,
            "judgment_id": digest("response-id"),
            "judge_provenance": {
                "provider": "fixture",
                "model": "fixture-judge-v1",
                "prompt_sha256": digest("judge prompt"),
            },
        }
    )


def test_provider_error_fails_hard_gate_without_exact_or_format_violations() -> None:
    case = response_case(
        constraints=HardConstraints(
            required_literals=("EXACT",),
            required_json_keys=("answer",),
            max_sentences=1,
        )
    )
    raw = raw_attempt(
        case,
        output=None,
        error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
    )

    scored = score_attempt(case, raw)

    assert not scored.hard_pass
    assert [(check.name, check.passed) for check in scored.checks] == [("provider.error", False)]
    assert not any(check.name.startswith(("exact.", "format.")) for check in scored.checks)


def test_required_and_forbidden_literals_are_independent_and_case_sensitive() -> None:
    case = response_case(
        constraints=HardConstraints(
            required_literals=("Alpha", "BETA", "https://example.test/x"),
            forbidden_literals=("secret", "NEVER"),
        ),
        rubric=SemanticRubric(required_facts=("do not literal-match this rubric",)),
    )

    scored = score_attempt(
        case,
        raw_attempt(case, output="Alpha beta https://example.test/x; NEVER."),
    )

    checks = {check.name: check for check in scored.checks}
    assert checks["exact.required_literal[0]"].passed
    assert not checks["exact.required_literal[1]"].passed
    assert checks["exact.required_literal[2]"].passed
    assert checks["exact.forbidden_literal[0]"].passed
    assert not checks["exact.forbidden_literal[1]"].passed
    assert all("do not literal-match" not in check.detail for check in scored.checks)
    assert not scored.hard_pass


def test_semantic_rubric_text_is_never_used_as_a_literal_check() -> None:
    case = response_case(
        rubric=SemanticRubric(
            required_facts=("a fact absent from the response",),
            material_warning="a warning absent from the response",
        )
    )

    scored = score_attempt(case, raw_attempt(case, output="Deterministically valid."))

    assert scored.hard_pass
    assert scored.checks == ()


@pytest.mark.parametrize("output", ["", " \t\n"])
def test_successful_blank_output_fails_an_explicit_check_and_keeps_raw_text(output: str) -> None:
    case = response_case()

    scored = score_attempt(case, raw_attempt(case, output=output))

    assert scored.raw.output_text == output
    assert [(check.name, check.passed) for check in scored.checks] == [
        ("format.nonblank_output", False)
    ]
    assert not scored.hard_pass
    assert not eligible_for_pairing(scored, require_semantic=False)


@pytest.mark.parametrize(
    ("output", "object_passed", "key_passed"),
    [
        (' {"answer": 42, "nested": {"other": true}} \n', True, True),
        ('{"nested": {"answer": 42}}', True, False),
        ('[ {"answer": 42} ]', False, False),
        ("null", False, False),
        ('{"answer": 42} trailing', False, False),
    ],
)
def test_required_json_keys_need_a_full_top_level_object(
    output: str,
    object_passed: bool,
    key_passed: bool,
) -> None:
    case = response_case(constraints=HardConstraints(required_json_keys=("answer", "missing")))

    scored = score_attempt(case, raw_attempt(case, output=output))

    checks = {check.name: check for check in scored.checks}
    assert checks["format.json_object"].passed is object_passed
    assert checks["format.required_json_key[answer]"].passed is key_passed
    assert not checks["format.required_json_key[missing]"].passed


@pytest.mark.parametrize(
    "output",
    [
        '{"answer": NaN}',
        '{"answer": Infinity}',
        '{"answer": -Infinity}',
        '```json\n{"answer": 1}\n```',
        'Result: {"answer": 1}',
    ],
)
def test_required_json_keys_reject_non_rfc_constants_fences_and_prose(output: str) -> None:
    case = response_case(constraints=HardConstraints(required_json_keys=("answer",)))

    scored = score_attempt(case, raw_attempt(case, output=output))

    checks = {check.name: check.passed for check in scored.checks}
    assert checks["format.json_object"] is False
    assert checks["format.required_json_key[answer]"] is False
    assert not scored.hard_pass


def test_declared_json_keys_are_an_exact_top_level_set() -> None:
    case = response_case(constraints=HardConstraints(required_json_keys=("answer", "confidence")))

    exact = score_attempt(case, raw_attempt(case, output='{"answer": 42, "confidence": "high"}'))
    extra = score_attempt(
        case,
        raw_attempt(
            case,
            output='{"answer": 42, "confidence": "high", "unexpected": true}',
        ),
    )

    assert exact.hard_pass
    assert {check.name: check.passed for check in exact.checks}["format.json_key_set"]
    assert not extra.hard_pass
    assert not {check.name: check.passed for check in extra.checks}["format.json_key_set"]


def test_deeply_nested_json_fails_the_check_without_aborting_scoring() -> None:
    case = response_case(constraints=HardConstraints(required_json_keys=("answer",)))
    output = "[" * 1_100 + "0" + "]" * 1_100

    scored = score_attempt(case, raw_attempt(case, output=output))

    checks = {check.name: check.passed for check in scored.checks}
    assert checks["format.json_object"] is False
    assert checks["format.required_json_key[answer]"] is False
    assert not scored.hard_pass


@pytest.mark.parametrize(
    ("output", "mapping_passed", "key_set_passed"),
    [
        ("status: unsafe\nreason: duplicate\nnext_step: deduplicate\n", True, True),
        ("status: unsafe\nreason: duplicate\n", True, False),
        (
            "status: unsafe\nreason: duplicate\nnext_step: deduplicate\nunexpected: true\n",
            True,
            False,
        ),
        ("- status\n- reason\n- next_step\n", False, False),
        ("status reason next_step", False, False),
        ("```yaml\nstatus: unsafe\nreason: duplicate\nnext_step: deduplicate\n```", False, False),
        (
            "status: unsafe\nreason: duplicate\nnext_step: deduplicate\ntrailing prose",
            False,
            False,
        ),
        ("status: unsafe\nstatus: duplicate\nreason: why\nnext_step: act\n", False, False),
        (
            "defaults: &defaults\n  reason: duplicate\nstatus: unsafe\n<<: *defaults\n"
            "next_step: act\n",
            False,
            False,
        ),
    ],
)
def test_required_yaml_keys_need_one_complete_exact_top_level_mapping(
    output: str,
    mapping_passed: bool,
    key_set_passed: bool,
) -> None:
    case = response_case(
        constraints=HardConstraints(required_yaml_keys=("status", "reason", "next_step"))
    )

    scored = score_attempt(case, raw_attempt(case, output=output))

    checks = {check.name: check.passed for check in scored.checks}
    assert checks["format.yaml_mapping"] is mapping_passed
    assert checks["format.yaml_key_set"] is key_set_passed
    assert scored.hard_pass is (mapping_passed and key_set_passed)


@pytest.mark.parametrize(
    "output",
    [
        "status: 2020-99-99\nreason: x\nnext_step: y\n",
        'status: !!int ""\nreason: x\nnext_step: y\n',
        "status: !!timestamp nope\nreason: x\nnext_step: y\n",
    ],
)
def test_yaml_constructor_failure_fails_the_check_without_aborting_scoring(output: str) -> None:
    case = response_case(
        constraints=HardConstraints(required_yaml_keys=("status", "reason", "next_step"))
    )

    scored = score_attempt(
        case,
        raw_attempt(case, output=output),
    )

    checks = {check.name: check.passed for check in scored.checks}
    assert checks["format.yaml_mapping"] is False
    assert checks["format.yaml_key_set"] is False
    assert not scored.hard_pass


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("  \n\t", 0),
        ('")] }', 1),
        ("No punctuation", 1),
        ("One... Two?! Three\uff01\uff1f Four\u3002", 4),
        ("What?!", 1),
        ("甲\u3002乙\uff01丙\uff1f", 3),
        ("Version v2.4.1 uses https://api.example.com/v1.", 1),
        ("Value 3.14 was approved by Dr. Smith.", 1),
        ("1. Install. 2. Verify.", 2),
        ('He said, "Ready?")', 1),
        ('Really?"!', 1),
        ("https://example.test/search?q=x.", 1),
        ("Use `foo.`", 1),
        ("Use `foo?bar` in the command.", 1),
        ("Run ```foo.\nbar?``` now.", 1),
        ("\u0433. \u041c\u043e\u0441\u043a\u0432\u0430", 1),
        ("\u0410. \u0421. \u041f\u0443\u0448\u043a\u0438\u043d", 1),
        ("\u0442.\u0435. \u043f\u0440\u0438\u043c\u0435\u0440", 1),
    ],
)
def test_count_sentences_handles_english_cjk_and_punctuation_runs(text: str, expected: int) -> None:
    assert count_sentences(text) == expected


def test_minimum_and_maximum_sentence_checks_are_separate() -> None:
    case = response_case(constraints=HardConstraints(min_sentences=2, max_sentences=3))

    too_short = score_attempt(case, raw_attempt(case, output="Only one"))
    within = score_attempt(case, raw_attempt(case, output="One. Two\uff01 Three?"))

    short_checks = {check.name: check.passed for check in too_short.checks}
    within_checks = {check.name: check.passed for check in within.checks}
    assert short_checks == {
        "format.min_sentences": False,
        "format.max_sentences": True,
    }
    assert within_checks == {
        "format.min_sentences": True,
        "format.max_sentences": True,
    }


def test_preserve_config_values_do_not_create_false_sentence_boundaries() -> None:
    case = response_case(
        constraints=HardConstraints(
            required_literals=("v2.4.1", "8080", "https://api.example.com/v1"),
            max_sentences=1,
        )
    )
    output = "Version v2.4.1 runs on port 8080 with endpoint https://api.example.com/v1."

    scored = score_attempt(case, raw_attempt(case, output=output))

    assert scored.hard_pass
    assert all(check.passed for check in scored.checks)


def test_score_attempt_rejects_case_prompt_mismatch_and_nonterminal() -> None:
    case = response_case()
    other = response_case(case_id="scoring-002-en")

    with pytest.raises(ValueError, match="case_id"):
        score_attempt(case, raw_attempt(other))
    with pytest.raises(ValueError, match="prompt_sha256"):
        score_attempt(case, raw_attempt(case, prompt_hash=digest("wrong")))
    with pytest.raises(ValueError, match="terminal"):
        score_attempt(case, raw_attempt(case, terminal=False))


def test_score_attempt_rejects_a_changed_case_definition_with_the_same_prompt() -> None:
    original = response_case()
    original_raw = raw_attempt(original)
    changed = original.model_copy(
        update={
            "semantic_rubric": SemanticRubric(
                required_facts=("A newly revised required fact.",),
            )
        }
    )

    with pytest.raises(ValueError, match="case_definition_sha256"):
        score_attempt(changed, original_raw)


def test_score_attempt_rejects_a_different_runner_version() -> None:
    case = response_case()
    incompatible = raw_attempt(case).model_copy(update={"runner_version": "0.0.0-incompatible"})

    with pytest.raises(ValueError, match="runner_version"):
        score_attempt(case, incompatible)


def test_score_terminal_attempts_ignores_retries_and_rejects_unknown_case() -> None:
    case = response_case()
    retry = raw_attempt(
        case,
        output=None,
        error=ErrorInfo(kind="timeout", message="again", retryable=True),
        terminal=False,
    )
    terminal = raw_attempt(case, output="Done.", attempt=2)

    assert score_terminal_attempts(
        {case.id: case},
        (
            retry,
            terminal,
        ),
    ) == (score_attempt(case, terminal),)

    unknown = raw_attempt(response_case(case_id="unknown-001-en"))
    with pytest.raises(ValueError, match="unknown case_id"):
        score_terminal_attempts({case.id: case}, (unknown,))


def test_pair_eligibility_requires_hard_and_optionally_semantic_pass() -> None:
    case = response_case()
    passing = score_attempt(case, raw_attempt(case))
    failing_case = response_case(
        case_id="scoring-002-en",
        constraints=HardConstraints(required_literals=("must",)),
    )
    failing = score_attempt(failing_case, raw_attempt(failing_case, output="short"))

    assert eligible_for_pairing(passing, require_semantic=False)
    assert not eligible_for_pairing(passing, require_semantic=True)
    assert not eligible_for_pairing(failing, require_semantic=False)
    assert eligible_for_pairing(with_judgment(passing, True), require_semantic=True)


def test_scored_attempt_integrity_rejects_nonterminal_and_incorrect_hard_gate() -> None:
    case = response_case()
    passing = score_attempt(case, raw_attempt(case))

    nonterminal = passing.model_dump(mode="python")
    nonterminal["raw"] = {
        **passing.raw.model_dump(mode="python"),
        "terminal": False,
    }
    with pytest.raises(ValidationError, match="terminal"):
        ScoredAttempt.model_validate(nonterminal)

    with pytest.raises(ValidationError, match="hard_pass"):
        ScoredAttempt.model_validate({**passing.model_dump(mode="python"), "hard_pass": False})

    failing_check = CheckResult(name="exact.required_literal[0]", passed=False, detail="missing")
    with pytest.raises(ValidationError, match="hard_pass"):
        ScoredAttempt.model_validate(
            {
                **passing.model_dump(mode="python"),
                "checks": (failing_check,),
                "hard_pass": True,
            }
        )


def test_scored_attempt_judgment_fields_are_coherent_and_only_on_hard_passes() -> None:
    case = response_case()
    passing = score_attempt(case, raw_attempt(case))
    provenance = JudgeProvenance(
        provider="fixture",
        model="fixture-judge-v1",
        prompt_sha256=digest("judge prompt"),
    )
    judgment_fields = {
        "semantic_pass": True,
        "judgment_id": digest("response-id"),
        "judge_provenance": provenance,
    }

    assert with_judgment(passing, True).judge_provenance == provenance
    for field in judgment_fields:
        with pytest.raises(ValidationError, match="all be set or all be null"):
            ScoredAttempt.model_validate(
                {
                    **passing.model_dump(mode="python"),
                    field: judgment_fields[field],
                }
            )

    failing_case = response_case(
        case_id="scoring-002-en",
        constraints=HardConstraints(required_literals=("required",)),
    )
    hard_failure = score_attempt(failing_case, raw_attempt(failing_case, output="missing"))
    with pytest.raises(ValidationError, match="hard-fail"):
        ScoredAttempt.model_validate({**hard_failure.model_dump(mode="python"), **judgment_fields})

    error_raw = raw_attempt(
        case,
        output=None,
        error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
    )
    provider_failure = score_attempt(case, error_raw)
    with pytest.raises(ValidationError, match="hard-fail"):
        ScoredAttempt.model_validate(
            {**provider_failure.model_dump(mode="python"), **judgment_fields}
        )


def test_scored_jsonl_round_trip_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    case = response_case()
    scored = (score_attempt(case, raw_attempt(case, output="Привет.")),)
    path = tmp_path / "nested" / "scored.jsonl"

    write_scored_jsonl(scored, path)

    assert load_scored_jsonl(path) == scored
    assert path.read_bytes().endswith(b"\n")
    assert "Привет" in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="refuse"):
        write_scored_jsonl((), path)


def test_pairing_and_scored_writer_revalidate_bypassed_models_before_output(
    tmp_path: Path,
) -> None:
    case = response_case()
    valid = score_attempt(case, raw_attempt(case))
    provider_error = score_attempt(
        case,
        raw_attempt(
            case,
            output=None,
            error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
        ),
    )
    tampered = provider_error.model_copy(update={"hard_pass": True})

    with pytest.raises(ValidationError, match="hard_pass"):
        eligible_for_pairing(tampered, require_semantic=False)

    path = tmp_path / "must-not-exist.jsonl"
    with pytest.raises(ValidationError, match="hard_pass"):
        write_scored_jsonl((valid, tampered), path)
    assert not path.exists()


@pytest.mark.parametrize(
    ("content", "line", "message"),
    [
        ("\n", 1, "blank"),
        ("{}\nnot-json\n", 1, "invalid scored attempt"),
        (json.dumps({"bad": True}), 1, "unterminated"),
    ],
)
def test_load_scored_jsonl_reports_path_and_line(
    tmp_path: Path,
    content: str,
    line: int,
    message: str,
) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{path}:{line}.*{message}"):
        load_scored_jsonl(path)


def test_load_scored_jsonl_reports_later_malformed_and_blank_lines(tmp_path: Path) -> None:
    case = response_case()
    valid = score_attempt(case, raw_attempt(case)).model_dump_json()

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text(f"{valid}\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{malformed}:2.*invalid scored attempt"):
        load_scored_jsonl(malformed)

    blank = tmp_path / "blank.jsonl"
    blank.write_text(f"{valid}\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{blank}:2.*blank"):
        load_scored_jsonl(blank)


def test_load_scored_jsonl_rejects_a_tampered_hard_gate(tmp_path: Path) -> None:
    case = response_case()
    valid = score_attempt(case, raw_attempt(case))
    tampered = {**valid.model_dump(mode="json"), "hard_pass": False}
    path = tmp_path / "tampered.jsonl"
    path.write_text(f"{json.dumps(tampered)}\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_scored_jsonl(path)
    assert str(exc_info.value).startswith(f"{path}:1:")
    assert "hard_pass" in str(exc_info.value)
