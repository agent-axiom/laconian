#!/usr/bin/env python3
"""Bounded exploratory comparison with a separate, blinded semantic phase."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import os
import random
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

if __package__:
    from . import exploratory_pilot as pilot
    from . import exploratory_protocol as protocol
else:
    import exploratory_pilot as pilot
    import exploratory_protocol as protocol

FORMAT = "exploratory-comparison-v1"
BUDGET = 75_000_000
SEED = 1729
REPETITIONS = 5
WALL_SECONDS = 330 * 60
PRICE_DATE = pilot.PRICE_DATE
PRICES = {**pilot.PRICES, "format": FORMAT}
LIMITATIONS = [
    "Exploratory authored cases; no statistical significance or generalization claim.",
    "Primary delta is concise minus if, within each requested and resolved model.",
    "Only matched case/repetition pairs passing hard and semantic checks enter brevity means.",
    "All paired comparisons are suppressed when generation or judgment coverage is incomplete.",
    "Nonreasoning output tokens are not a visible-text token count.",
    "One serial exposure ledger covers generation and judging; no retry or resume.",
    "Exposure cap assumes frozen prices and input-token bounds, not an invoice guarantee.",
    "Raw bytes are retained except bounded prefixes for oversized bodies "
    "and withheld credential echoes.",
]


def snapshot(root: Path) -> dict[str, bytes]:
    sources = pilot.snapshot(root)
    for name, relative in (
        ("comparison.py", "tools/exploratory_comparison.py"),
        ("protocol.py", "tools/exploratory_protocol.py"),
        ("sentences.py", "tools/exploratory_sentences.py"),
        ("response-cases.yaml", "evals/exploratory/response-cases.yaml"),
    ):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise pilot.Stop("invalid_source_file")
        sources[name] = path.read_bytes()
        sources[name].decode("utf-8")
    if pilot.digest(sources["response-cases.yaml"]) != protocol.CASE_SHA256:
        raise pilot.Stop("case_pin_mismatch")
    return sources


def request_record(request: dict[str, Any]) -> dict[str, Any]:
    bound = len(pilot.encoded(request)) + 65_536
    if bound > 272_000:
        raise pilot.Stop("input_bound_exceeded")
    rates = PRICES["models"][request["model"]]
    return {
        "model": request["model"],
        "request": request,
        "request_sha256": pilot.digest(pilot.encoded(request)),
        "input_bound": bound,
        "reservation_micros": (
            pilot.priced(bound, max(rates["input"], rates["read"], rates["write"]))
            + pilot.priced(request["max_output_tokens"], rates["output"])
            + 4
        ),
    }


def build_plan(sources: dict[str, bytes], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    instructions = {
        "baseline": sources["baseline.txt"],
        "concise": sources["concise.txt"],
        "caveman": sources["caveman.SKILL.md"],
        "if": sources["if.SKILL.md"],
    }
    blocks = [
        (model, case, repetition)
        for model in pilot.MODELS
        for case in cases
        for repetition in range(1, REPETITIONS + 1)
    ]
    rng = random.Random(SEED)
    rng.shuffle(blocks)
    plan = []
    for model, case, repetition in blocks:
        arms = list(pilot.ARMS)
        rng.shuffle(arms)
        for arm in arms:
            instruction = instructions[arm]
            request = {
                "model": model,
                "instructions": instruction.decode() if arm != "baseline" else None,
                "input": case["prompt"],
                "store": False,
                "tools": [],
                "max_output_tokens": pilot.OUTPUT_LIMIT,
                "reasoning": {"effort": "medium"},
                "text": {"verbosity": "medium"},
                "service_tier": "default",
                "prompt_cache_options": pilot.CACHE.copy(),
            }
            plan.append(
                {
                    **request_record(request),
                    "index": len(plan) + 1,
                    "phase": "generation",
                    "case": case["id"],
                    "scenario_id": case["scenario_id"],
                    "locale": case["locale"],
                    "arm": arm,
                    "repetition": repetition,
                    "arm_sha256": pilot.digest(instruction),
                    "prompt_sha256": pilot.digest(case["prompt"].encode()),
                    "case_sha256": pilot.digest(pilot.encoded(case)),
                }
            )
    return plan


def response_text(response: Any) -> tuple[str, bool]:
    output = pilot.member(response, "output", "output")
    if not isinstance(output, list):
        raise pilot.Stop("invalid_output")
    parts = []
    refused = False
    for item in output:
        if not isinstance(item, dict):
            raise pilot.Stop("invalid_output_item")
        if item.get("type") != "message":
            continue
        if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
            raise pilot.Stop("invalid_message")
        for part in item["content"]:
            if not isinstance(part, dict):
                raise pilot.Stop("invalid_output_part")
            if part.get("type") == "refusal":
                refused = True
            elif part.get("type") == "output_text":
                if not isinstance(part.get("text"), str):
                    raise pilot.Stop("invalid_output_text")
                parts.append(part["text"])
    return "\n".join(parts), refused


def judge_plan(
    eligible: list[tuple[dict[str, Any], str]], cases: dict[str, dict[str, Any]], start: int
) -> list[dict[str, Any]]:
    # Separate random stream; IDs do not encode model, arm, case, length, or generation index.
    rng = random.Random(SEED + 1)
    queue = list(eligible)
    rng.shuffle(queue)
    records = []
    for generation, answer in queue:
        blind_id = f"{rng.getrandbits(128):032x}"
        request = protocol.judge_request(cases[generation["case"]], answer, blind_id)
        records.append(
            {
                **request_record(request),
                "index": start + len(records) + 1,
                "phase": "judgment",
                "blind_id": blind_id,
                "generation_index": generation["index"],
                "case": generation["case"],
                "generation_model": generation["model"],
                "arm": generation["arm"],
                "repetition": generation["repetition"],
            }
        )
    return records


def execute(
    output: Path,
    plan: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    key: str,
    transport: pilot.Transport,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    started = clock()
    settled = outstanding = 0
    terminals: list[dict[str, Any]] = []
    eligible: list[tuple[dict[str, Any], str]] = []
    lookup = {case["id"]: case for case in cases}
    stop_reason = None
    ledger_path = output / "ledger.jsonl"
    pilot.persist(ledger_path, b"", key)

    def event(value: dict[str, Any]) -> None:
        body = pilot.encoded(value)
        if key and key.encode() in body:
            raise pilot.Stop("credential_in_artifact")
        with ledger_path.open("ab") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())

    def dispatch(record: dict[str, Any]) -> bool:
        nonlocal settled, outstanding, stop_reason
        if clock() - started >= WALL_SECONDS:
            stop_reason = "wall_clock_cutoff"
            return False
        reservation = record["reservation_micros"]
        if settled + outstanding + reservation > BUDGET:
            stop_reason = "budget_exhausted"
            return False
        outstanding += reservation
        event(
            {
                "event": "reserved",
                "phase": record["phase"],
                "index": record["index"],
                "reservation_micros": reservation,
                "settled_micros": settled,
                "outstanding_micros": outstanding,
                "request_sha256": record["request_sha256"],
            }
        )
        result = {
            "index": record["index"],
            "phase": record["phase"],
            "requested_model": record["model"],
            "case": record["case"],
            "arm": record["arm"],
            "repetition": record["repetition"],
            "request_sha256": record["request_sha256"],
        }
        if record["phase"] == "judgment":
            result.update(blind_id=record["blind_id"], generation_index=record["generation_index"])
        category = "unknown"
        try:
            try:
                status, request_id, raw = transport(pilot.encoded(record["request"]), key)
            except (Exception, KeyboardInterrupt) as exc:
                raise pilot.Stop(
                    "transport_timeout" if isinstance(exc, TimeoutError) else "transport_error"
                ) from None
            if type(raw) is not bytes:
                raise pilot.Stop("invalid_transport_body")
            result["truncated"] = len(raw) > pilot.RAW_LIMIT
            if pilot.credential_echo(raw, key):
                result["body_withheld"] = True
                raise pilot.Stop("credential_echo_body_withheld")
            raw = raw[: pilot.RAW_LIMIT]
            path = output / "responses" / f"{record['index']:04d}.bin"
            pilot.persist(path, raw, key)
            result.update(raw_sha256=pilot.digest(raw), raw_path=str(path.relative_to(output)))
            if type(status) is not int or not 100 <= status <= 599:
                raise pilot.Stop("invalid_http_status")
            result["http_status"] = status
            if (
                isinstance(request_id, str)
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id)
                and key not in request_id
            ):
                result["request_id"] = request_id
            if result["truncated"]:
                raise pilot.Stop("response_too_large")
            if status != 200:
                category = "error"
                raise pilot.Stop("http_auth" if status in (401, 403) else "http_error")
            response = pilot.strict_json(raw)
            result.update(
                pilot.account_usage(
                    response, record, output_limit=record["request"]["max_output_tokens"]
                )
            )
        except pilot.Stop as exc:
            stop_reason = str(exc)
            result.update(status=category, error=stop_reason)
            event({"event": "terminal", **result, "outstanding_micros": outstanding})
            terminals.append(result)
            print(
                f"phase={record['phase']} requests={len(terminals)} settled_micros={settled} "
                f"outstanding_micros={outstanding} stopped=1",
                flush=True,
            )
            return False

        # From this point usage is certain: failures affect quality, not settlement.
        result["response_status"] = response["status"]
        result["output_characters"] = None
        try:
            answer, refused = response_text(response)
            result["output_characters"] = len(answer)
            answer.encode("utf-8")
            if response["status"] != "completed":
                raise pilot.Stop("response_incomplete")
            if refused:
                raise pilot.Stop("response_refusal")
            if not answer.strip():
                raise pilot.Stop("blank_output")
            if record["phase"] == "generation":
                result["quality"] = protocol.hard_checks(lookup[record["case"]], answer)
                result["judge_eligible"] = True
                eligible.append((record, answer))
                result["status"] = "completed"
            else:
                result["judgment"] = protocol.parse_judgment(
                    answer, lookup[record["case"]], record["blind_id"]
                )
                pilot.encoded(result["judgment"])
                result["status"] = "valid"
        except (pilot.Stop, UnicodeError) as exc:
            result.pop("judgment", None)
            result.update(
                status="failed" if record["phase"] == "generation" else "invalid",
                error=str(exc) if isinstance(exc, pilot.Stop) else "invalid_output_unicode",
            )
        settled += result["settled_micros"]
        outstanding -= reservation
        event(
            {
                "event": "settled",
                **result,
                "total_settled_micros": settled,
                "outstanding_micros": outstanding,
            }
        )
        terminals.append(result)
        print(
            f"phase={record['phase']} requests={len(terminals)} settled_micros={settled} "
            f"outstanding_micros={outstanding} stopped=0",
            flush=True,
        )
        return True

    for record in plan:
        if not dispatch(record):
            break
    judges = []
    try:
        judges = judge_plan(eligible, lookup, len(plan))
    except pilot.Stop as exc:
        stop_reason = stop_reason or str(exc)
    pilot.persist(output / "judge-plan.json", pilot.encoded(judges), key)
    if stop_reason is None:
        for record in judges:
            if not dispatch(record):
                break
    generations = [r for r in terminals if r["phase"] == "generation"]
    judgments = [r for r in terminals if r["phase"] == "judgment"]
    return {
        "format": FORMAT,
        "mode": "live",
        "planned": len(plan),
        "generation_completed": sum(r["status"] == "completed" for r in generations),
        "generation_failed": sum(r["status"] != "completed" for r in generations),
        "generation_missing": len(plan) - len(generations),
        "generation_campaign_complete": len(generations) == len(plan)
        and all("settled_micros" in r for r in generations),
        "judge_eligible": len(eligible),
        "judgment_planned": len(judges),
        "judgment_valid": sum(r["status"] == "valid" for r in judgments),
        "judgment_invalid": sum(r["status"] != "valid" for r in judgments),
        "judgment_missing": len(eligible) - len(judgments),
        "settled_micros": settled,
        "outstanding_micros": outstanding,
        "budget_micros": BUDGET,
        "phase_costs_micros": {
            phase: sum(r.get("settled_micros", 0) for r in terminals if r["phase"] == phase)
            for phase in ("generation", "judgment")
        },
        "unknown": sum(r["status"] == "unknown" for r in terminals),
        "stop_reason": stop_reason,
        "terminals": terminals,
    }


def build_report(plan: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    terminals = summary["terminals"]
    generation = {r["index"]: r for r in terminals if r["phase"] == "generation"}
    judgment = {r["generation_index"]: r for r in terminals if r["phase"] == "judgment"}
    coverage = (
        summary["generation_campaign_complete"]
        and summary["judgment_valid"] == summary["judge_eligible"]
    )

    def passed(record: dict[str, Any]) -> bool:
        terminal = generation.get(record["index"], {})
        judge = judgment.get(record["index"], {})
        return (
            terminal.get("status") == "completed"
            and terminal.get("quality", {}).get("hard_pass") is True
            and judge.get("status") == "valid"
            and judge.get("judgment", {}).get("semantic_pass") is True
        )

    metrics = {
        "billed_output_tokens": lambda r: r["usage"]["output_tokens"],
        "nonreasoning_output_tokens": lambda r: r["usage"]["nonreasoning_output_tokens"],
        "output_characters": lambda r: r["output_characters"],
    }
    models = {}
    for model in pilot.MODELS:
        records = [r for r in plan if r["model"] == model]
        arms = {}
        for arm in pilot.ARMS:
            arm_records = [r for r in records if r["arm"] == arm]
            results = [generation[r["index"]] for r in arm_records if r["index"] in generation]
            judges = [judgment[r["index"]] for r in arm_records if r["index"] in judgment]
            valid = [r for r in judges if r["status"] == "valid"]
            complete = [r for r in results if r["status"] == "completed"]
            arms[arm] = {
                "planned": len(arm_records),
                "completed": len(complete),
                "failed": len(results) - len(complete),
                "missing": len(arm_records) - len(results),
                "hard_pass": sum(r.get("quality", {}).get("hard_pass") is True for r in complete),
                "hard_fail": sum(r.get("quality", {}).get("hard_pass") is False for r in complete),
                "semantic_pass": sum(r["judgment"]["semantic_pass"] is True for r in valid),
                "semantic_fail": sum(r["judgment"]["semantic_pass"] is False for r in valid),
                "semantic_missing": len(arm_records) - len(valid),
                "generation_cost_micros": sum(r.get("settled_micros", 0) for r in results),
                "judgment_cost_micros": sum(r.get("settled_micros", 0) for r in judges),
                "unknown_accounting": sum("settled_micros" not in r for r in results + judges),
            }
        paired = []
        candidates = {(r["case"], r["repetition"]) for r in records}
        keyed = {(r["case"], r["repetition"], r["arm"]): r for r in records}
        missing = failed = 0
        for case, repetition in sorted(candidates):
            left = keyed.get((case, repetition, "concise"))
            right = keyed.get((case, repetition, "if"))
            if (
                left is None
                or right is None
                or any(r["index"] not in generation for r in (left, right))
            ):
                missing += 1
            elif not passed(left) or not passed(right):
                failed += 1
            else:
                paired.append((generation[left["index"]], generation[right["index"]]))
        means = None
        delta = None
        if coverage and paired:
            means = {
                arm: {
                    name: sum(read(pair[i]) for pair in paired) / len(paired)
                    for name, read in metrics.items()
                }
                for i, arm in enumerate(("concise", "if"))
            }
            delta = {name: means["concise"][name] - means["if"][name] for name in metrics}
        models[model] = {
            "arms": arms,
            "primary": {
                "comparison": "concise - if",
                "planned_pairs": len(candidates),
                "paired": len(paired) if coverage else None,
                "missing_pairs": missing,
                "failed_or_unjudged_pairs": failed,
                "excluded": len(candidates) - len(paired) if coverage else len(candidates),
                "means": means,
                "concise_minus_if": delta,
            },
        }
    return {
        "format": FORMAT,
        "mode": summary["mode"],
        "paired_comparisons_available": coverage,
        "suppression_reason": None if coverage else "incomplete_generation_or_judgment_coverage",
        "models": models,
        "phase_costs_micros": summary["phase_costs_micros"],
        "settled_micros": summary["settled_micros"],
        "outstanding_micros": summary["outstanding_micros"],
        "limitations": LIMITATIONS,
    }


def report_markdown(report: dict[str, Any]) -> bytes:
    lines = [
        "# Exploratory comparison",
        "",
        f"Mode: {report['mode']}. No inferential claims.",
        "",
        f"Settled: {report['settled_micros']} microUSD; outstanding exposure: "
        f"{report['outstanding_micros']} microUSD.",
        "",
        "Generation and judgment costs are reported separately; unknown usage is not zero cost.",
        "",
    ]
    if not report["paired_comparisons_available"]:
        lines.extend(
            ["Paired comparisons suppressed: incomplete generation or judgment coverage.", ""]
        )
    for model, result in report["models"].items():
        lines.extend(
            [
                f"## {model}",
                "",
                "| Arm | Planned | Completed | Failed | Missing | Hard pass/fail | "
                "Semantic pass/fail/missing | Generation microUSD | Judge microUSD |",
                "|---|---:|---:|---:|---:|---|---|---:|---:|",
            ]
        )
        for arm, counts in result["arms"].items():
            lines.append(
                f"| {arm} | {counts['planned']} | {counts['completed']} | {counts['failed']} | "
                f"{counts['missing']} | {counts['hard_pass']}/{counts['hard_fail']} | "
                f"{counts['semantic_pass']}/{counts['semantic_fail']}/"
                f"{counts['semantic_missing']} | "
                f"{counts['generation_cost_micros']} | {counts['judgment_cost_micros']} |"
            )
        primary = result["primary"]
        lines.extend(
            [
                "",
                f"Primary concise - if: paired={primary['paired']}; "
                f"excluded={primary['excluded']}; missing={primary['missing_pairs']}; "
                f"failed or unjudged={primary['failed_or_unjudged_pairs']}.",
                "",
            ]
        )
        if primary["means"] is not None:
            lines.extend(
                ["| Metric | Concise mean | If mean | Concise minus if |", "|---|---:|---:|---:|"]
            )
            for metric, delta in primary["concise_minus_if"].items():
                lines.append(
                    f"| {metric} | {primary['means']['concise'][metric]:.3f} | "
                    f"{primary['means']['if'][metric]:.3f} | {delta:.3f} |"
                )
            lines.append("")
    lines.extend(["## Limitations", "", *(f"- {item}" for item in LIMITATIONS), ""])
    return "\n".join(lines).encode()


def dry_summary(planned: int) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "mode": "dry-run",
        "planned": planned,
        "generation_completed": 0,
        "generation_failed": 0,
        "generation_missing": planned,
        "generation_campaign_complete": False,
        "judge_eligible": 0,
        "judgment_planned": 0,
        "judgment_valid": 0,
        "judgment_invalid": 0,
        "judgment_missing": 0,
        "settled_micros": 0,
        "outstanding_micros": 0,
        "budget_micros": BUDGET,
        "phase_costs_micros": {"generation": 0, "judgment": 0},
        "unknown": 0,
        "stop_reason": None,
        "terminals": [],
    }


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    transport: pilot.Transport | None = None,
    today: dt.date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--confirm-cost", choices=("75",))
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision):
            raise pilot.Stop("invalid_revision")
        sources = snapshot(root or Path(__file__).resolve().parents[1])
        cases = protocol.load_cases(sources["response-cases.yaml"])
        plan = build_plan(sources, cases)
        key = ""
        if args.live:
            if args.confirm_cost != "75":
                raise pilot.Stop("cost_confirmation_required")
            expected = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_RUN_ATTEMPT": "1",
            }
            if any(os.environ.get(name) != value for name, value in expected.items()):
                raise pilot.Stop("workflow_context_required")
            if not 0 <= ((today or dt.datetime.now(dt.UTC).date()) - PRICE_DATE).days <= 7:
                raise pilot.Stop("pricing_snapshot_stale")
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
                raise pilot.Stop("missing_or_invalid_api_key")
        output = args.output
        output.mkdir(mode=0o700)
        pilot.sync_directory(output.parent)
        for directory in ("sources", "responses"):
            (output / directory).mkdir(mode=0o700)
        pilot.sync_directory(output)
        for name, body in sources.items():
            pilot.persist(output / "sources" / name, body, key)
        pilot.persist(output / "prices.json", pilot.encoded(PRICES), key)
        pilot.persist(output / "generation-plan.json", pilot.encoded(plan), key)
        manifest = {
            "format": FORMAT,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "revision": args.revision.lower(),
            "mode": "live" if args.live else "dry-run",
            "planned": len(plan),
            "budget_micros": BUDGET,
            "models": pilot.MODELS,
            "arms": pilot.ARMS,
            "seed": SEED,
            "repetitions": REPETITIONS,
            "wall_clock_cutoff_seconds": WALL_SECONDS,
            "source_sha256": {name: pilot.digest(body) for name, body in sources.items()},
            "prices_sha256": pilot.digest(pilot.encoded(PRICES)),
            "generation_plan_sha256": pilot.digest(pilot.encoded(plan)),
            "dependencies": {"PyYAML": importlib.metadata.version("PyYAML")},
            "judge_protocol_sha256": pilot.digest(
                pilot.encoded(
                    {
                        "schema": getattr(protocol, "SCHEMA", None),
                        "authority": getattr(protocol, "AUTHORITY", None),
                    }
                )
            ),
            "limitations": LIMITATIONS,
        }
        pilot.persist(output / "manifest.json", pilot.encoded(manifest), key)
        if args.dry_run:
            pilot.persist(output / "ledger.jsonl", b"", key)
            pilot.persist(output / "judge-plan.json", pilot.encoded([]), key)
            summary = dry_summary(len(plan))
        else:
            summary = execute(output, plan, cases, key, transport or pilot.https_transport)
        summary["judge_plan_sha256"] = pilot.digest((output / "judge-plan.json").read_bytes())
        summary["ledger_sha256"] = pilot.digest((output / "ledger.jsonl").read_bytes())
        pilot.persist(output / "summary.json", pilot.encoded(summary), key)
        report = build_report(plan, summary)
        report["provenance"] = {
            "manifest_sha256": pilot.digest(pilot.encoded(manifest)),
            "summary_sha256": pilot.digest(pilot.encoded(summary)),
            "ledger_sha256": summary["ledger_sha256"],
            "judge_plan_sha256": summary["judge_plan_sha256"],
        }
        pilot.persist(output / "report.json", pilot.encoded(report), key)
        pilot.persist(output / "report.md", report_markdown(report), key)
        return (
            0
            if args.dry_run
            or (
                summary["stop_reason"] is None
                and summary["generation_campaign_complete"]
                and summary["judgment_valid"] == summary["judge_eligible"]
            )
            else 1
        )
    except (OSError, UnicodeError, pilot.Stop) as exc:
        code = str(exc) if isinstance(exc, pilot.Stop) else "local_io_error"
        print("exploratory comparison stopped: " + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
