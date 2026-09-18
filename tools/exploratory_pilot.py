#!/usr/bin/env python3
"""Standalone, fail-closed exploratory API pilot; never executes model output."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import math
import os
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

FORMAT = "exploratory-pilot-v1"
MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-astra")
ARMS = ("baseline", "concise", "caveman", "if")
BUDGET = 5_000_000
OUTPUT_LIMIT = 1024
RAW_LIMIT = 2 * 1024 * 1024
PRICE_DATE = dt.date(2026, 9, 18)
CACHE = {"mode": "explicit", "ttl": "30m"}
PRICES = {
    "format": FORMAT,
    "date": PRICE_DATE.isoformat(),
    "source": "https://developers.openai.com/api/docs/pricing",
    "scope": "global default tier; no region or pro-mode adjustment",
    "unit": "USD microdollars per million tokens",
    "models": {
        "gpt-5.6-sol": {
            "input": 4_000_000,
            "read": 400_000,
            "write": 5_000_000,
            "output": 20_000_000,
        },
        "gpt-5.6-terra": {
            "input": 2_000_000,
            "read": 200_000,
            "write": 2_500_000,
            "output": 12_000_000,
        },
        "gpt-5.6-luna": {"input": 200_000, "read": 20_000, "write": 250_000, "output": 1_200_000},
        "gpt-6-astra": {
            "input": 10_000_000,
            "read": 1_000_000,
            "write": 12_500_000,
            "output": 50_000_000,
        },
    },
}
PINNED = {
    "evals/baselines/caveman/SKILL.md": (
        "1eddf7055618153869975678d9ff36635602a3aa333f8b4cc0787f12de75b6f8"
    ),
    "evals/baselines/caveman/SOURCE.md": (
        "8aa76311ea6273848242b1fcdd3542c47683fdeb7118395afb5aafb4709d081d"
    ),
    "LICENSES/CAVEMAN-MIT.txt": "f0abc56b6f49ab2e285bb6e6723f028abb7ebd4fe0e242bbdc2b4dded0ace8b9",
}
SOURCE_FILES = {
    "caveman.SKILL.md": "evals/baselines/caveman/SKILL.md",
    "caveman.SOURCE.md": "evals/baselines/caveman/SOURCE.md",
    "caveman.LICENSE.txt": "LICENSES/CAVEMAN-MIT.txt",
    "if.SKILL.md": "skills/if/SKILL.md",
}
LITERALS = ("v2.4.1", "8080", "https://api.example.com/v1")
CASES = (
    {
        "id": "preserve-config-en",
        "scenario_id": "preserve-config",
        "locale": "en",
        "prompt": (
            "Summarize this deployment configuration without changing any values: version v2.4.1, "
            "port 8080, and endpoint https://api.example.com/v1."
        ),
        "required_literals": LITERALS,
    },
    {
        "id": "preserve-config-ru",
        "scenario_id": "preserve-config",
        "locale": "ru",
        "prompt": (
            "Кратко изложи эту конфигурацию развёртывания, не меняя значения: версия v2.4.1, "
            "порт 8080 и адрес https://api.example.com/v1."
        ),
        "required_literals": LITERALS,
    },
)
Transport = Callable[[bytes, str], tuple[int, str | None, bytes]]


class Stop(Exception):
    """A fixed, non-provider-controlled diagnostic code."""


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def persist(path: Path, body: bytes, key: str = "") -> None:
    if key and key.encode() in body:
        raise Stop("credential_in_artifact")
    with path.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


def snapshot(root: Path) -> dict[str, bytes]:
    sources = {"baseline.txt": b"", "concise.txt": b"Answer concisely."}
    for name, relative in SOURCE_FILES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise Stop("invalid_source_file")
        body = path.read_bytes()
        if relative in PINNED and digest(body) != PINNED[relative]:
            raise Stop("caveman_pin_mismatch")
        body.decode("utf-8")
        sources[name] = body
    sources["launcher.py"] = Path(__file__).read_bytes()
    return sources


def priced(tokens: int, rate: int) -> int:
    return (tokens * rate + 999_999) // 1_000_000


def build_plan(sources: dict[str, bytes]) -> list[dict[str, Any]]:
    instructions = {
        "baseline": sources["baseline.txt"],
        "concise": sources["concise.txt"],
        "caveman": sources["caveman.SKILL.md"],
        "if": sources["if.SKILL.md"],
    }
    rng = random.Random(1729)
    plan = []
    for model in MODELS:
        rates = PRICES["models"][model]
        for case in CASES:
            order = list(ARMS)
            rng.shuffle(order)
            for arm in order:
                instruction = instructions[arm]
                prompt = case["prompt"]
                bound = len(instruction) + len(prompt.encode()) + 65_536
                if bound > 272_000:
                    raise Stop("input_bound_exceeded")
                request = {
                    "model": model,
                    "instructions": instruction.decode() if arm != "baseline" else None,
                    "input": prompt,
                    "store": False,
                    "tools": [],
                    "max_output_tokens": OUTPUT_LIMIT,
                    "reasoning": {"effort": "medium"},
                    "text": {"verbosity": "medium"},
                    "service_tier": "default",
                    "prompt_cache_options": CACHE.copy(),
                }
                plan.append(
                    {
                        "index": len(plan) + 1,
                        "model": model,
                        "case": case["id"],
                        "scenario_id": case["scenario_id"],
                        "locale": case["locale"],
                        "arm": arm,
                        "repetition": 1,
                        "arm_sha256": digest(instruction),
                        "prompt_sha256": digest(prompt.encode()),
                        "case_sha256": digest(encoded(case)),
                        "request_sha256": digest(encoded(request)),
                        "input_bound": bound,
                        "reservation_micros": (
                            priced(bound, max(rates["input"], rates["read"], rates["write"]))
                            + priced(OUTPUT_LIMIT, rates["output"])
                            + 4
                        ),
                        "request": request,
                    }
                )
    return plan


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise Stop("duplicate_json_key")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise Stop("nonfinite_json")

    def floating(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise Stop("nonfinite_json")
        return number

    try:
        return json.loads(
            raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=floating
        )
    except (ValueError, UnicodeError, RecursionError):
        raise Stop("malformed_json") from None


def member(value: Any, name: str, path: str) -> Any:
    if not isinstance(value, dict) or name not in value:
        raise Stop("missing_" + path)
    return value[name]


def integer(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise Stop("invalid_" + path)
    return value


def account(response: Any, record: dict[str, Any]) -> dict[str, Any]:
    if member(response, "status", "status") != "completed":
        raise Stop("response_not_completed")
    if member(response, "error", "error") is not None:
        raise Stop("response_error")
    if member(response, "model", "model") != record["model"]:
        raise Stop("resolved_model_mismatch")
    if member(response, "service_tier", "service_tier") != "default":
        raise Stop("service_tier_mismatch")
    if member(response, "prompt_cache_options", "prompt_cache_options") != CACHE:
        raise Stop("cache_contract_mismatch")
    usage = member(response, "usage", "usage")
    counts = {}
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        counts[field] = integer(member(usage, field, field), field)
    for field, container in (
        ("cached_tokens", "input_tokens_details"),
        ("cache_write_tokens", "input_tokens_details"),
        ("reasoning_tokens", "output_tokens_details"),
    ):
        details = member(usage, container, container)
        counts[field] = integer(member(details, field, field), field)
    incoming, outgoing = counts["input_tokens"], counts["output_tokens"]
    cached, written = counts["cached_tokens"], counts["cache_write_tokens"]
    if (
        counts["total_tokens"] != incoming + outgoing
        or cached + written > incoming
        or counts["reasoning_tokens"] > outgoing
        or incoming > record["input_bound"]
        or outgoing > OUTPUT_LIMIT
    ):
        raise Stop("inconsistent_usage")
    output = member(response, "output", "output")
    text = []
    if not isinstance(output, list):
        raise Stop("invalid_output")
    for item in output:
        if isinstance(item, dict) and item.get("type") == "message":
            if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
                raise Stop("invalid_message")
            for part in item["content"]:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    if not isinstance(part.get("text"), str):
                        raise Stop("invalid_output_text")
                    text.append(part["text"])
    answer = "\n".join(text)
    if not answer.strip():
        raise Stop("blank_output")
    rates = PRICES["models"][record["model"]]
    ordinary = incoming - cached - written
    components = {
        "ordinary_input": priced(ordinary, rates["input"]),
        "cached_input": priced(cached, rates["read"]),
        "cache_write_input": priced(written, rates["write"]),
        "output_including_reasoning": priced(outgoing, rates["output"]),
    }
    cost = sum(components.values())
    if cost > record["reservation_micros"]:
        raise Stop("charge_exceeds_reservation")
    missing = [literal for literal in LITERALS if literal not in answer]
    return {
        "requested_model": record["model"],
        "resolved_model": response["model"],
        "usage": {
            **counts,
            "ordinary_input_tokens": ordinary,
            "nonreasoning_output_tokens": outgoing - counts["reasoning_tokens"],
        },
        "cost_components_micros": components,
        "settled_micros": cost,
        "quality": {"hard_pass": not missing, "missing_literals": missing},
    }


def response_read_limit(key: str) -> int:
    # A JSON escape occupies at most six bytes for each ASCII credential character.
    return RAW_LIMIT + min(6 * len(key), RAW_LIMIT) + 1


def credential_echo(raw: bytes, key: str) -> bool:
    """Screen bounded literal/JSON-escaped credentials independently of JSON validity."""
    raw = raw[: response_read_limit(key)]
    if key.encode() in raw:
        return True
    patterns = []
    short_escapes = {'"': b'\\"', "\\": b"\\\\", "/": b"\\/"}
    for char in key:
        hexadecimal = "".join(
            f"[{digit}{digit.upper()}]" if digit in "abcdef" else digit
            for digit in f"{ord(char):02x}"
        ).encode()
        choices = [re.escape(char.encode()), rb"\\u00" + hexadecimal]
        if char in short_escapes:
            choices.append(re.escape(short_escapes[char]))
        patterns.append(b"(?:" + b"|".join(choices) + b")")
    return re.search(b"".join(patterns), raw) is not None


def https_transport(body: bytes, key: str) -> tuple[int, str | None, bytes]:
    connection = http.client.HTTPSConnection("api.openai.com", 443, timeout=120)
    try:
        connection.request(
            "POST",
            "/v1/responses",
            body=body,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("x-request-id"),
            response.read(response_read_limit(key)),
        )
    finally:
        connection.close()


def execute(
    output: Path, plan: list[dict[str, Any]], key: str, transport: Transport
) -> dict[str, Any]:
    settled = outstanding = completed = failed = hard_pass = unknown = 0
    terminals = []
    stop_reason = None
    ledger_path = output / "ledger.jsonl"
    persist(ledger_path, b"", key)

    def event(value: dict[str, Any]) -> None:
        body = encoded(value)
        if key and key.encode() in body:
            raise Stop("credential_in_artifact")
        with ledger_path.open("ab") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())

    for record in plan:
        reservation = record["reservation_micros"]
        if settled + outstanding + reservation > BUDGET:
            stop_reason = "budget_exhausted"
            break
        outstanding += reservation
        event(
            {
                "event": "reserved",
                "index": record["index"],
                "reservation_micros": reservation,
                "settled_micros": settled,
                "outstanding_micros": outstanding,
                "request_sha256": record["request_sha256"],
            }
        )
        result: dict[str, Any] = {"index": record["index"], "requested_model": record["model"]}
        category = "unknown"
        try:
            try:
                status, request_id, raw = transport(encoded(record["request"]), key)
            except (Exception, KeyboardInterrupt) as exc:
                code = "transport_timeout" if isinstance(exc, TimeoutError) else "transport_error"
                raise Stop(code) from None
            if type(raw) is not bytes:
                raise Stop("invalid_transport_body")
            truncated = len(raw) > RAW_LIMIT
            result["truncated"] = truncated
            if credential_echo(raw, key):
                result["body_withheld"] = True
                raise Stop("credential_echo_body_withheld")
            raw = raw[:RAW_LIMIT]
            raw_path = output / "responses" / f"{record['index']:04d}.bin"
            persist(raw_path, raw, key)
            result["raw_sha256"] = digest(raw)
            result["raw_path"] = str(raw_path.relative_to(output))
            if type(status) is not int or not 100 <= status <= 599:
                raise Stop("invalid_http_status")
            result["http_status"] = status
            if (
                isinstance(request_id, str)
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id)
                and key not in request_id
            ):
                result["request_id"] = request_id
            if truncated:
                raise Stop("response_too_large")
            if status != 200:
                category = "error"
                raise Stop("http_auth" if status in (401, 403) else "http_error")
            parsed = strict_json(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("model"), str):
                result["resolved_model"] = parsed["model"]
            result.update(account(parsed, record))
        except Stop as exc:
            failed += 1
            unknown += category == "unknown"
            stop_reason = str(exc)
            result.update({"status": category, "error": stop_reason})
            event({"event": "terminal", **result})
            terminals.append(result)
            break
        settled += result["settled_micros"]
        outstanding -= reservation
        completed += 1
        hard_pass += result["quality"]["hard_pass"]
        result["status"] = "completed"
        event({"event": "settled", **result, "outstanding_micros": outstanding})
        terminals.append(result)
    return {
        "format": FORMAT,
        "mode": "live",
        "planned": len(plan),
        "completed": completed,
        "failed": failed,
        "unknown": unknown,
        "not_attempted": len(plan) - completed - failed,
        "hard_pass": hard_pass,
        "hard_fail": completed - hard_pass,
        "settled_micros": settled,
        "outstanding_micros": outstanding,
        "budget_micros": BUDGET,
        "stop_reason": stop_reason,
        "terminals": terminals,
    }


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    transport: Transport | None = None,
    today: dt.date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--confirm-cost", choices=("5",))
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision):
            raise Stop("invalid_revision")
        sources = snapshot(root or Path(__file__).resolve().parents[1])
        plan = build_plan(sources)
        key = ""
        if args.live:
            if args.confirm_cost != "5":
                raise Stop("cost_confirmation_required")
            expected = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_RUN_ATTEMPT": "1",
            }
            if any(os.environ.get(name) != value for name, value in expected.items()):
                raise Stop("workflow_context_required")
            date = today or dt.datetime.now(dt.UTC).date()
            if not 0 <= (date - PRICE_DATE).days <= 7:
                raise Stop("pricing_snapshot_stale")
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key or any(ord(char) < 33 or ord(char) > 126 for char in key):
                raise Stop("missing_or_invalid_api_key")
        output = args.output
        output.mkdir(mode=0o700)
        sync_directory(output.parent)
        for directory in ("sources", "responses"):
            (output / directory).mkdir(mode=0o700)
        sync_directory(output)
        for name, body in sources.items():
            persist(output / "sources" / name, body, key)
        persist(output / "prices.json", encoded(PRICES), key)
        persist(output / "plan.json", encoded(plan), key)
        manifest = {
            "format": FORMAT,
            "revision": args.revision.lower(),
            "mode": "live" if args.live else "dry-run",
            "planned": len(plan),
            "budget_micros": BUDGET,
            "models": MODELS,
            "arms": ARMS,
            "seed": 1729,
            "repetitions": 1,
            "cases": CASES,
            "source_sha256": {name: digest(body) for name, body in sources.items()},
            "prices_sha256": digest(encoded(PRICES)),
            "plan_sha256": digest(encoded(plan)),
            "limitations": [
                "Exploratory one-scenario EN/RU pilot, one repetition, no semantic judge.",
                "Hard-literal checks do not establish semantic task success.",
                "No comparative gains, paired brevity claims, or inferential metrics.",
                "Nonreasoning output tokens are not a visible-text token count.",
                "Exposure cap assumes frozen prices and the input-token bound; "
                "not an invoice guarantee.",
                "Stop on uncertainty; retain reservation; no retries or resume.",
                "Raw response bytes are preserved unless oversized (bounded prefix) "
                "or credential echo "
                "(entire body withheld; not an unchanged raw record).",
            ],
        }
        persist(output / "manifest.json", encoded(manifest), key)
        if args.dry_run:
            summary = {
                "format": FORMAT,
                "mode": "dry-run",
                "planned": len(plan),
                "completed": 0,
                "failed": 0,
                "unknown": 0,
                "not_attempted": len(plan),
                "hard_pass": 0,
                "hard_fail": 0,
                "settled_micros": 0,
                "outstanding_micros": 0,
                "budget_micros": BUDGET,
                "stop_reason": None,
                "terminals": [],
            }
        else:
            summary = execute(output, plan, key, transport or https_transport)
        persist(output / "summary.json", encoded(summary), key)
        return 0 if args.dry_run or summary["completed"] == len(plan) else 1
    except (OSError, UnicodeError, Stop) as exc:
        code = str(exc) if isinstance(exc, Stop) else "local_io_error"
        print("exploratory pilot stopped: " + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
