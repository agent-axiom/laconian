import json
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from laconian_eval.models import (
    ErrorInfo,
    HardConstraints,
    JudgeProvenance,
    PriceSnapshot,
    RawAttempt,
    ResponseCase,
    ScoredAttempt,
    TokenUsageModel,
)
from laconian_eval.reporting import summarize, write_markdown_report, write_summary_json
from laconian_eval.scoring import score_attempt


def digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def case(
    *,
    case_id: str = "report-001-en",
    required: tuple[str, ...] = (),
    json_keys: tuple[str, ...] = (),
) -> ResponseCase:
    return ResponseCase(
        id=case_id,
        scenario_id=case_id.removesuffix("-en").removesuffix("-ru"),
        locale="ru" if case_id.endswith("-ru") else "en",
        category="direct",
        prompt=f"Prompt for {case_id}.",
        hard_constraints=HardConstraints(
            required_literals=required,
            required_json_keys=json_keys,
        ),
    )


def raw(
    response_case: ResponseCase,
    *,
    arm: str,
    output: str | None,
    usage: TokenUsageModel | None = None,
    error: ErrorInfo | None = None,
    attempt: int = 1,
    run_id: str = "run-1",
    manifest_hash: str = "a" * 64,
    repetition: int = 0,
) -> RawAttempt:
    return RawAttempt(
        run_id=run_id,
        manifest_sha256=manifest_hash,
        case_id=response_case.id,
        arm=arm,
        repetition=repetition,
        attempt=attempt,
        terminal=True,
        retry_of_attempt=attempt - 1 if attempt > 1 else None,
        prompt_sha256=digest(response_case.prompt),
        instruction_sha256=digest(f"{arm}-instruction"),
        provider="fake",
        model="fixture-v1",
        started_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
        elapsed_ms=5,
        output_text=output,
        usage=usage,
        error=error,
    )


def scored(
    response_case: ResponseCase,
    *,
    arm: str,
    output: str,
    output_tokens: int,
    input_tokens: int = 10,
    cached_tokens: int | None = 0,
    semantic: bool | None = None,
    provenance: JudgeProvenance | None = None,
    repetition: int = 0,
    run_id: str = "run-1",
    manifest_hash: str = "a" * 64,
) -> ScoredAttempt:
    result = score_attempt(
        response_case,
        raw(
            response_case,
            arm=arm,
            output=output,
            usage=TokenUsageModel(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_input_tokens=cached_tokens,
            ),
            repetition=repetition,
            run_id=run_id,
            manifest_hash=manifest_hash,
        ),
    )
    if semantic is None:
        return result
    selected_provenance = provenance or JudgeProvenance(
        provider="fixture",
        model="fixture-judge-v1",
        prompt_sha256=digest("judge prompt"),
    )
    judgment_id = digest(
        ":".join(
            (
                result.raw.run_id,
                result.raw.manifest_sha256,
                result.raw.case_id,
                result.raw.arm,
                str(result.raw.repetition),
                result.raw.output_text or "",
            )
        )
    )
    return ScoredAttempt.model_validate(
        {
            **result.model_dump(mode="python"),
            "semantic_pass": semantic,
            "judgment_id": judgment_id,
            "judge_provenance": selected_provenance,
        }
    )


def test_shorter_failed_if_is_excluded_and_paired_delta_is_right_minus_left() -> None:
    first = case(required=("REQUIRED",))
    second = case(case_id="report-002-en", required=("OK",))
    rows = (
        scored(first, arm="if", output="tiny", output_tokens=1),
        scored(first, arm="concise", output="REQUIRED valid response", output_tokens=6),
        scored(second, arm="if", output="OK short", output_tokens=3),
        scored(second, arm="concise", output="OK a longer response", output_tokens=8),
    )

    summary = summarize(rows)

    assert summary.paired.eligible_pairs == 1
    assert summary.paired.median_output_token_delta == 5
    assert summary.paired.median_output_character_delta == len("OK a longer response") - len(
        "OK short"
    )


def test_pairing_uses_full_instance_identity_and_ignores_missing_mates() -> None:
    response_case = case(required=("OK",))
    rows = (
        scored(response_case, arm="if", output="OK", output_tokens=1, run_id="run-a"),
        scored(
            response_case,
            arm="concise",
            output="OK cross run",
            output_tokens=4,
            run_id="run-b",
        ),
        scored(
            response_case,
            arm="if",
            output="OK two",
            output_tokens=2,
            repetition=1,
            run_id="run-a",
        ),
        scored(
            response_case,
            arm="concise",
            output="OK paired two long",
            output_tokens=7,
            repetition=1,
            run_id="run-a",
        ),
    )

    summary = summarize(rows)

    assert summary.paired.eligible_pairs == 1
    assert summary.paired.median_output_token_delta == 5


def test_pair_token_delta_requires_both_usage_but_char_delta_does_not() -> None:
    response_case = case(required=("OK",))
    left = score_attempt(
        response_case,
        raw(response_case, arm="if", output="OK short", usage=None),
    )
    right = scored(
        response_case,
        arm="concise",
        output="OK considerably longer",
        output_tokens=7,
    )

    paired = summarize((left, right)).paired

    assert paired.eligible_pairs == 1
    assert paired.median_output_token_delta is None
    assert paired.median_output_character_delta == len("OK considerably longer") - len("OK short")


def test_paired_token_metric_is_the_median_of_per_pair_deltas() -> None:
    rows = []
    token_counts = ((1, 11), (100, 101), (101, 201))
    for index, (if_tokens, concise_tokens) in enumerate(token_counts, start=1):
        response_case = case(case_id=f"report-{index:03}-en")
        rows.extend(
            (
                scored(
                    response_case,
                    arm="if",
                    output="i",
                    output_tokens=if_tokens,
                ),
                scored(
                    response_case,
                    arm="concise",
                    output="concise",
                    output_tokens=concise_tokens,
                ),
            )
        )

    paired = summarize(tuple(rows)).paired

    assert paired.eligible_pairs == 3
    assert paired.median_output_token_delta == 10


def test_pairing_rejects_duplicate_arm_in_one_instance() -> None:
    response_case = case()
    duplicate = scored(response_case, arm="if", output="one", output_tokens=1)

    with pytest.raises(ValueError, match=r"duplicate arm.*instance"):
        summarize((duplicate, duplicate))


def test_summarize_revalidates_a_bypassed_failed_check() -> None:
    response_case = case(required=("REQUIRED",))
    failed = scored(response_case, arm="if", output="missing", output_tokens=1)
    tampered = failed.model_copy(update={"hard_pass": True})

    with pytest.raises(ValidationError, match="hard_pass"):
        summarize((tampered,))


def test_arm_metrics_count_attempts_errors_and_violation_categories() -> None:
    exact_case = case(required=("EXACT",))
    format_case = case(case_id="report-002-en", json_keys=("answer",))
    error_case = case(case_id="report-003-en", required=("IGNORED",), json_keys=("x",))
    provider_error = score_attempt(
        error_case,
        raw(
            error_case,
            arm="baseline",
            output=None,
            error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
            attempt=3,
        ),
    )
    rows = (
        scored(exact_case, arm="baseline", output="wrong", output_tokens=2),
        scored(format_case, arm="baseline", output="not json", output_tokens=3),
        provider_error,
    )

    summary = summarize(rows)
    metrics = summary.arms[0]

    assert summary.raw_attempts == 5
    assert summary.terminal_records == 3
    assert metrics.total == 3
    assert metrics.hard_passed == 0
    assert metrics.semantic_judged == 0
    assert metrics.provider_errors == 1
    assert metrics.retry_attempts == 2
    assert metrics.exact_violations == 1
    assert metrics.format_violations == 2
    assert metrics.median_output_tokens == 2.5
    assert metrics.median_output_characters == (len("wrong") + len("not json")) / 2


def test_semantic_status_is_nullable_and_semantic_gate_requires_full_coverage() -> None:
    response_case = case()
    not_judged = scored(
        response_case,
        arm="if",
        output="answer",
        output_tokens=2,
        semantic=None,
    )

    hard_summary = summarize((not_judged,))

    assert hard_summary.quality_gate == "hard"
    assert hard_summary.arms[0].semantic_passed is None
    assert hard_summary.arms[0].semantic_judged == 0
    with pytest.raises(ValueError, match="semantic judgment coverage"):
        summarize((not_judged,), require_semantic=True)

    failed = scored(
        response_case,
        arm="if",
        output="answer",
        output_tokens=2,
        semantic=False,
    )
    semantic_summary = summarize((failed,), require_semantic=True)
    assert semantic_summary.quality_gate == "semantic"
    assert semantic_summary.arms[0].semantic_passed == 0
    assert semantic_summary.arms[0].semantic_judged == 1


def test_semantic_gate_does_not_require_judgments_for_hard_failures() -> None:
    response_case = case(required=("REQUIRED",))
    hard_failure = scored(
        response_case,
        arm="if",
        output="missing",
        output_tokens=1,
        semantic=None,
    )

    summary = summarize((hard_failure,), require_semantic=True)

    assert summary.arms[0].hard_passed == 0
    assert summary.arms[0].semantic_passed is None
    assert summary.arms[0].semantic_judged == 0


def test_semantic_pairing_requires_both_sides_to_pass_semantic_gate() -> None:
    response_case = case()
    rows = (
        scored(
            response_case,
            arm="if",
            output="short",
            output_tokens=2,
            semantic=True,
        ),
        scored(
            response_case,
            arm="concise",
            output="longer",
            output_tokens=4,
            semantic=False,
        ),
    )

    assert summarize(rows).paired.eligible_pairs == 1
    assert summarize(rows, require_semantic=True).paired.eligible_pairs == 0


def snapshot(*, cached_rate: float | None = 1.0) -> PriceSnapshot:
    return PriceSnapshot(
        effective_date=date(2026, 1, 1),
        source_url="https://example.test/pricing",
        input_per_million=2.0,
        cached_input_per_million=cached_rate,
        output_per_million=8.0,
    )


def test_price_estimate_subtracts_cached_input_and_uses_separate_rates() -> None:
    response_case = case()
    row = scored(
        response_case,
        arm="if",
        output="answer",
        output_tokens=5,
        input_tokens=10,
        cached_tokens=4,
    )

    metrics = summarize((row,), price_snapshot=snapshot()).arms[0]

    assert metrics.price is not None
    assert metrics.price.input_usd == pytest.approx(6 * 2 / 1_000_000)
    assert metrics.price.cached_input_usd == pytest.approx(4 * 1 / 1_000_000)
    assert metrics.price.output_usd == pytest.approx(5 * 8 / 1_000_000)
    assert metrics.price.total_usd == pytest.approx(56 / 1_000_000)


def test_price_cached_rate_falls_back_and_missing_success_usage_suppresses_cost() -> None:
    response_case = case()
    with_usage = scored(
        response_case,
        arm="if",
        output="answer",
        output_tokens=5,
        input_tokens=10,
        cached_tokens=4,
    )
    without_usage = score_attempt(
        response_case,
        raw(
            response_case,
            arm="if",
            output="another",
            usage=None,
            repetition=1,
        ),
    )

    fallback = summarize((with_usage,), price_snapshot=snapshot(cached_rate=None)).arms[0]
    partial = summarize((with_usage, without_usage), price_snapshot=snapshot()).arms[0]

    assert fallback.price is not None
    assert fallback.price.cached_input_usd == pytest.approx(4 * 2 / 1_000_000)
    assert partial.price is None


def test_price_requires_known_cache_accounting_and_at_least_one_success() -> None:
    response_case = case()
    unknown_cache = scored(
        response_case,
        arm="if",
        output="answer",
        output_tokens=5,
        cached_tokens=None,
    )
    provider_error = score_attempt(
        response_case,
        raw(
            response_case,
            arm="baseline",
            output=None,
            error=ErrorInfo(kind="timeout", message="Timed out.", retryable=True),
        ),
    )
    explicit_zero_cache = scored(
        response_case,
        arm="concise",
        output="answer",
        output_tokens=5,
        cached_tokens=0,
    )

    assert summarize((unknown_cache,), price_snapshot=snapshot()).arms[0].price is None
    assert summarize((provider_error,), price_snapshot=snapshot()).arms[0].price is None
    assert summarize((explicit_zero_cache,), price_snapshot=snapshot()).arms[0].price is not None


def test_summary_and_markdown_writers_are_deterministic_and_refuse_existing_paths(
    tmp_path: Path,
) -> None:
    response_case = case()
    rows = (
        scored(
            response_case,
            arm="if",
            output="short",
            output_tokens=2,
            semantic=False,
        ),
        scored(
            response_case,
            arm="concise",
            output="a longer answer",
            output_tokens=5,
            semantic=True,
        ),
    )
    summary = summarize(rows, price_snapshot=snapshot())
    json_path = tmp_path / "nested" / "summary.json"
    report_path = tmp_path / "nested" / "report.md"

    write_summary_json(summary, json_path)
    write_markdown_report(summary, report_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == "1"
    assert json_path.read_bytes().endswith(b"\n")
    markdown = report_path.read_text(encoding="utf-8")
    assert "Provider errors" in markdown
    assert "Exact violations" in markdown
    assert "Format violations" in markdown
    assert "not judged" not in markdown
    assert "1/1 (100.0%)" in markdown
    assert "0/1 passed (0.0%)" in markdown
    assert "1/1 hard-pass coverage (100.0%)" in markdown
    assert "concise - if" in markdown
    assert "positive means `if` is shorter" in markdown
    assert "(input - cached input)" in markdown
    assert "2026-01-01" in markdown
    assert "https://example.test/pricing" in markdown
    assert "fixture-judge-v1" in markdown
    assert digest("judge prompt") in markdown
    assert summary.judge_provenance == (
        JudgeProvenance(
            provider="fixture",
            model="fixture-judge-v1",
            prompt_sha256=digest("judge prompt"),
        ),
    )
    for forbidden in ("composite score", "leaderboard", "rank"):
        assert forbidden not in markdown.lower()

    with pytest.raises(FileExistsError, match="refuse"):
        write_summary_json(summary, json_path)
    with pytest.raises(FileExistsError, match="refuse"):
        write_markdown_report(summary, report_path)


def test_markdown_distinguishes_not_judged_from_semantic_failure(tmp_path: Path) -> None:
    response_case = case()
    unjudged = scored(
        response_case,
        arm="if",
        output="short",
        output_tokens=2,
        semantic=None,
    )
    failed = scored(
        response_case,
        arm="concise",
        output="longer",
        output_tokens=3,
        semantic=False,
    )
    report = tmp_path / "report.md"

    write_markdown_report(summarize((unjudged, failed)), report)

    markdown = report.read_text(encoding="utf-8")
    assert "not judged" in markdown
    assert "0/1 passed (0.0%)" in markdown
    assert "1/1 hard-pass coverage (100.0%)" in markdown


def test_markdown_shows_partial_semantic_coverage_and_unique_sorted_provenance(
    tmp_path: Path,
) -> None:
    response_case = case()
    first_provenance = JudgeProvenance(
        provider="alpha",
        model="judge-a",
        prompt_sha256="1" * 64,
    )
    second_provenance = JudgeProvenance(
        provider="zeta",
        model="judge-z",
        prompt_sha256="2" * 64,
    )
    rows = (
        scored(
            response_case,
            arm="if",
            output="judged z",
            output_tokens=2,
            semantic=True,
            provenance=second_provenance,
            repetition=1,
        ),
        scored(
            response_case,
            arm="if",
            output="not judged",
            output_tokens=2,
            repetition=2,
        ),
        scored(
            response_case,
            arm="if",
            output="judged a",
            output_tokens=2,
            semantic=False,
            provenance=first_provenance,
            repetition=0,
        ),
    )

    summary = summarize(rows)
    report = tmp_path / "partial.md"
    write_markdown_report(summary, report)
    markdown = report.read_text(encoding="utf-8")

    assert summary.judge_provenance == (first_provenance, second_provenance)
    assert summary.arms[0].semantic_judged == 2
    assert summary.arms[0].semantic_passed == 1
    assert "1/2 passed (50.0%)" in markdown
    assert "2/3 hard-pass coverage (66.7%)" in markdown
    assert markdown.index("judge-a") < markdown.index("judge-z")
