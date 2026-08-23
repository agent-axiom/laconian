import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from laconian_eval.models import (
    ErrorInfo,
    HardConstraints,
    RawAttempt,
    ResponseCase,
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
        run_id=run_id,
        manifest_sha256=manifest_hash or digest("manifest-1"),
        case_id=case.id,
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
    ("text", "expected"),
    [
        ("", 0),
        ("  \n\t", 0),
        ("No punctuation", 1),
        ("One... Two?! Three\uff01\uff1f Four\u3002", 4),
        ("What?!", 1),
        ("甲\u3002乙\uff01丙\uff1f", 3),
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


def test_score_attempt_rejects_case_prompt_mismatch_and_nonterminal() -> None:
    case = response_case()
    other = response_case(case_id="scoring-002-en")

    with pytest.raises(ValueError, match="case_id"):
        score_attempt(case, raw_attempt(other))
    with pytest.raises(ValueError, match="prompt_sha256"):
        score_attempt(case, raw_attempt(case, prompt_hash=digest("wrong")))
    with pytest.raises(ValueError, match="terminal"):
        score_attempt(case, raw_attempt(case, terminal=False))


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
    assert eligible_for_pairing(
        passing.model_copy(update={"semantic_pass": True}), require_semantic=True
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
