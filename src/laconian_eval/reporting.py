import json
from collections.abc import Sequence
from pathlib import Path
from statistics import median
from typing import Literal, cast

from laconian_eval.models import (
    ArmMetrics,
    PairedMetrics,
    PriceEstimate,
    PriceSnapshot,
    RunSummary,
    ScoredAttempt,
    TokenUsageModel,
)
from laconian_eval.scoring import _revalidate_scored_attempts, eligible_for_pairing

ArmName = Literal["baseline", "concise", "caveman", "if"]
_ARM_ORDER: tuple[ArmName, ...] = ("baseline", "concise", "caveman", "if")


def _optional_median(values: Sequence[int]) -> float | None:
    return float(median(values)) if values else None


def _price_estimate(
    attempts: Sequence[ScoredAttempt], snapshot: PriceSnapshot
) -> PriceEstimate | None:
    successful = [attempt for attempt in attempts if attempt.raw.error is None]
    if not successful or any(
        attempt.raw.usage is None or attempt.raw.usage.cached_input_tokens is None
        for attempt in successful
    ):
        return None

    usages = cast(
        list[TokenUsageModel],
        [attempt.raw.usage for attempt in successful],
    )
    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    for usage in usages:
        assert usage.cached_input_tokens is not None
        cached = usage.cached_input_tokens
        input_tokens += usage.input_tokens - cached
        cached_tokens += cached
        output_tokens += usage.output_tokens

    cached_rate = (
        snapshot.cached_input_per_million
        if snapshot.cached_input_per_million is not None
        else snapshot.input_per_million
    )
    input_usd = input_tokens * snapshot.input_per_million / 1_000_000
    cached_input_usd = cached_tokens * cached_rate / 1_000_000
    output_usd = output_tokens * snapshot.output_per_million / 1_000_000
    return PriceEstimate(
        input_usd=input_usd,
        cached_input_usd=cached_input_usd,
        output_usd=output_usd,
        total_usd=input_usd + cached_input_usd + output_usd,
    )


def _arm_metrics(
    arm: ArmName,
    attempts: Sequence[ScoredAttempt],
    price_snapshot: PriceSnapshot | None,
) -> ArmMetrics:
    generated = [attempt for attempt in attempts if attempt.raw.error is None]
    token_counts = [
        attempt.raw.usage.output_tokens for attempt in generated if attempt.raw.usage is not None
    ]
    character_counts = [len(cast(str, attempt.raw.output_text)) for attempt in generated]
    judged = [attempt for attempt in attempts if attempt.semantic_pass is not None]
    semantic_passed = (
        sum(attempt.hard_pass and attempt.semantic_pass is True for attempt in judged)
        if judged
        else None
    )
    return ArmMetrics(
        arm=arm,
        total=len(attempts),
        hard_passed=sum(attempt.hard_pass for attempt in attempts),
        semantic_passed=semantic_passed,
        semantic_judged=len(judged),
        provider_errors=sum(attempt.raw.error is not None for attempt in attempts),
        retry_attempts=sum(attempt.raw.attempt - 1 for attempt in attempts),
        exact_violations=sum(
            not check.passed and check.name.startswith("exact.")
            for attempt in attempts
            for check in attempt.checks
        ),
        format_violations=sum(
            not check.passed and check.name.startswith("format.")
            for attempt in attempts
            for check in attempt.checks
        ),
        median_output_tokens=_optional_median(token_counts),
        median_output_characters=_optional_median(character_counts),
        price=(_price_estimate(attempts, price_snapshot) if price_snapshot is not None else None),
    )


def _instance_key(attempt: ScoredAttempt) -> tuple[str, str, str, int]:
    raw = attempt.raw
    return raw.run_id, raw.manifest_sha256, raw.case_id, raw.repetition


def _group_instances(
    scored: Sequence[ScoredAttempt],
) -> dict[tuple[str, str, str, int], dict[ArmName, ScoredAttempt]]:
    instances: dict[tuple[str, str, str, int], dict[ArmName, ScoredAttempt]] = {}
    for attempt in scored:
        key = _instance_key(attempt)
        arms = instances.setdefault(key, {})
        arm = attempt.raw.arm
        if arm in arms:
            raise ValueError(f"duplicate arm {arm!r} in benchmark instance {key!r}")
        arms[arm] = attempt
    return instances


def _paired_metrics(
    instances: dict[tuple[str, str, str, int], dict[ArmName, ScoredAttempt]],
    *,
    require_semantic: bool,
) -> PairedMetrics:
    token_deltas: list[int] = []
    character_deltas: list[int] = []
    eligible_pairs = 0
    for arms in instances.values():
        left = arms.get("if")
        right = arms.get("concise")
        if left is None or right is None:
            continue
        if not (
            eligible_for_pairing(left, require_semantic)
            and eligible_for_pairing(right, require_semantic)
        ):
            continue
        eligible_pairs += 1
        assert left.raw.output_text is not None
        assert right.raw.output_text is not None
        character_deltas.append(len(right.raw.output_text) - len(left.raw.output_text))
        if left.raw.usage is not None and right.raw.usage is not None:
            token_deltas.append(right.raw.usage.output_tokens - left.raw.usage.output_tokens)
    return PairedMetrics(
        eligible_pairs=eligible_pairs,
        median_output_token_delta=_optional_median(token_deltas),
        median_output_character_delta=_optional_median(character_deltas),
    )


def summarize(
    scored: Sequence[ScoredAttempt],
    *,
    require_semantic: bool = False,
    price_snapshot: PriceSnapshot | None = None,
) -> RunSummary:
    validated_scored = _revalidate_scored_attempts(scored)
    for attempt in validated_scored:
        if not attempt.raw.terminal:
            raise ValueError("summaries accept terminal raw records only")
        if require_semantic and attempt.hard_pass and attempt.semantic_pass is None:
            raise ValueError("semantic judgment coverage is incomplete for hard-pass attempts")

    instances = _group_instances(validated_scored)
    by_arm: dict[ArmName, list[ScoredAttempt]] = {}
    for attempt in validated_scored:
        by_arm.setdefault(attempt.raw.arm, []).append(attempt)

    arms = tuple(
        _arm_metrics(arm, by_arm[arm], price_snapshot) for arm in _ARM_ORDER if arm in by_arm
    )
    provenance_by_key = {
        (provenance.provider, provenance.model, provenance.prompt_sha256): provenance
        for attempt in validated_scored
        if (provenance := attempt.judge_provenance) is not None
    }
    judge_provenance = tuple(provenance_by_key[key] for key in sorted(provenance_by_key))
    return RunSummary(
        quality_gate="semantic" if require_semantic else "hard",
        raw_attempts=sum(attempt.raw.attempt for attempt in validated_scored),
        terminal_records=len(validated_scored),
        arms=arms,
        paired=_paired_metrics(instances, require_semantic=require_semantic),
        price_snapshot=price_snapshot,
        judge_provenance=judge_provenance,
    )


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"{path}: refuse to overwrite existing path")
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text_exclusive(path: Path, content: str) -> None:
    _refuse_existing(path)
    try:
        with path.open("x", encoding="utf-8") as output_file:
            output_file.write(content)
    except FileExistsError as exc:
        raise FileExistsError(f"{path}: refuse to overwrite existing path") from exc


def write_summary_json(summary: RunSummary, path: Path) -> None:
    content = json.dumps(
        summary.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    _write_text_exclusive(path, f"{content}\n")


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def _percentage(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{100 * numerator / denominator:.1f}%"


def _hard_pass_label(metrics: ArmMetrics) -> str:
    return (
        f"{metrics.hard_passed}/{metrics.total} ({_percentage(metrics.hard_passed, metrics.total)})"
    )


def _semantic_label(metrics: ArmMetrics) -> str:
    coverage = (
        f"{metrics.semantic_judged}/{metrics.hard_passed} hard-pass coverage "
        f"({_percentage(metrics.semantic_judged, metrics.hard_passed)})"
    )
    if metrics.semantic_passed is None:
        return f"not judged; {coverage}"
    return (
        f"{metrics.semantic_passed}/{metrics.semantic_judged} passed "
        f"({_percentage(metrics.semantic_passed, metrics.semantic_judged)}); {coverage}"
    )


def _price_label(price: PriceEstimate | None) -> str:
    return "n/a" if price is None else f"${price.total_usd:.8f}"


def _markdown(summary: RunSummary) -> str:
    lines = [
        "# Laconian benchmark report",
        "",
        f"Quality gate: `{summary.quality_gate}`",
        "",
        f"Raw attempts represented: {summary.raw_attempts}",
        f"Terminal records: {summary.terminal_records}",
        "",
        "## Per-arm results",
        "",
        (
            "| Arm | Terminal | Hard passed | Semantic | Provider errors | "
            "Exact violations | Format violations | Retries | Median output tokens | "
            "Median output characters | Estimated cost |"
        ),
        ("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|"),
    ]
    for metrics in summary.arms:
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{metrics.arm}`",
                    str(metrics.total),
                    _hard_pass_label(metrics),
                    _semantic_label(metrics),
                    str(metrics.provider_errors),
                    str(metrics.exact_violations),
                    str(metrics.format_violations),
                    str(metrics.retry_attempts),
                    _format_metric(metrics.median_output_tokens),
                    _format_metric(metrics.median_output_characters),
                    _price_label(metrics.price),
                )
            )
            + " |"
        )

    lines.extend(
        (
            "",
            "Provider errors, exact-value violations, and format violations are reported "
            "separately.",
            "",
            "## Paired `if` versus `concise`",
            "",
            "Delta formula: `concise - if`; positive means `if` is shorter.",
            f"Eligible pairs: {summary.paired.eligible_pairs}",
            (
                "Median output-token delta: "
                f"{_format_metric(summary.paired.median_output_token_delta)}"
            ),
            (
                "Median output-character delta: "
                f"{_format_metric(summary.paired.median_output_character_delta)}"
            ),
            "",
        )
    )
    lines.extend(("## Semantic judge provenance", ""))
    if summary.judge_provenance:
        lines.extend(
            (
                f"- `{provenance.provider}` / `{provenance.model}`; judge-prompt "
                f"SHA-256 `{provenance.prompt_sha256}`"
            )
            for provenance in summary.judge_provenance
        )
    else:
        lines.append("No semantic judgments attached.")
    lines.extend(("", "## Price estimate", ""))
    snapshot = summary.price_snapshot
    if snapshot is None:
        lines.append("Not estimated: no dated price snapshot was supplied.")
    else:
        cached_rate = (
            snapshot.cached_input_per_million
            if snapshot.cached_input_per_million is not None
            else snapshot.input_per_million
        )
        lines.extend(
            (
                (
                    "Formula per million tokens: `(input - cached input) * input rate + "
                    "cached input * cached-input rate + output * output rate`."
                ),
                (
                    f"Snapshot: {snapshot.effective_date.isoformat()}; source: "
                    f"{snapshot.source_url}."
                ),
                (
                    f"Rates (USD): input {snapshot.input_per_million:g}, cached input "
                    f"{cached_rate:g}, output {snapshot.output_per_million:g}."
                ),
            )
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(summary: RunSummary, path: Path) -> None:
    _write_text_exclusive(path, _markdown(summary))
