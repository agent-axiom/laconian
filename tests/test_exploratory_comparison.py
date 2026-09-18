"""Offline controller tests with synthetic responses; never benchmark evidence."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "exploratory_comparison.py"
KEY = "offline-comparison-key-123456789"
REVISION = "2" * 40
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
    "OPENAI_API_KEY": KEY,
}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "comparison controller is missing")
        spec = importlib.util.spec_from_file_location("tools.exploratory_comparison", SCRIPT)
        self.c = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.c)
        self.p = self.c.pilot
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / "run"
        self.calls = []
        self.cases = [
            {
                "id": f"case-{i}",
                "scenario_id": f"scenario-{i // 2}",
                "locale": "en" if i % 2 == 0 else "ru",
                "prompt": f"Answer item {i}",
                "semantic_rubric": {"required_facts": ["The answer is valid."]},
            }
            for i in range(24)
        ]
        self.sources = {
            "baseline.txt": b"",
            "concise.txt": b"Answer concisely.",
            "caveman.SKILL.md": b"Synthetic caveman instruction.",
            "if.SKILL.md": b"Synthetic if instruction.",
        }
        self.plan = self.c.build_plan(self.sources, self.cases)

    def small_plan(self):
        records = [
            r
            for r in self.plan
            if r["model"] == self.p.MODELS[0] and r["case"] == "case-0" and r["repetition"] == 1
        ]
        return [{**r, "index": index} for index, r in enumerate(records, 1)]

    def response(self, request, text="valid answer"):
        return {
            "model": request["model"],
            "status": "completed",
            "error": None,
            "service_tier": "default",
            "prompt_cache_options": self.p.CACHE.copy(),
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "total_tokens": 125,
                "input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 30},
                "output_tokens_details": {"reasoning_tokens": 10},
            },
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
        }

    def transport(self, body, key):
        self.assertEqual(key, KEY)
        request = json.loads(body)
        self.calls.append(request)
        ledger = [
            json.loads(line) for line in (self.output / "ledger.jsonl").read_text().splitlines()
        ]
        self.assertEqual(ledger[-1]["event"], "reserved")
        self.assertEqual(ledger[-1]["index"], len(self.calls))
        self.assertGreater(ledger[-1]["outstanding_micros"], 0)
        return 200, "req_synthetic", self.p.encoded(self.response(request))

    def judge_request(self, case, answer, blind_id):
        return {
            "model": self.p.MODELS[0],
            "instructions": "Synthetic judge protocol",
            "input": json.dumps({"prompt": case["prompt"], "answer": answer, "id": blind_id}),
            "store": False,
            "tools": [],
            "max_output_tokens": 768,
            "reasoning": {"effort": "low"},
            "text": {"verbosity": "low"},
            "service_tier": "default",
            "prompt_cache_options": self.p.CACHE.copy(),
        }

    def run_campaign(self, transport=None, plan=None, clock=None):
        self.output.mkdir()
        (self.output / "responses").mkdir()
        with (
            patch.object(
                self.c.protocol, "hard_checks", side_effect=lambda c, t: {"hard_pass": t != "wrong"}
            ),
            patch.object(self.c.protocol, "judge_request", side_effect=self.judge_request),
            patch.object(self.c.protocol, "parse_judgment", return_value={"semantic_pass": True}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return self.c.execute(
                self.output,
                plan or self.small_plan(),
                self.cases,
                KEY,
                transport or self.transport,
                **({"clock": clock} if clock else {}),
            )

    def test_plan_balances_unique_keys_randomized_blocks_and_fixed_requests(self):
        self.assertEqual(len(self.plan), 1920)
        self.assertEqual(self.plan, self.c.build_plan(self.sources, self.cases))
        keys = Counter((r["model"], r["case"], r["repetition"], r["arm"]) for r in self.plan)
        self.assertEqual(len(keys), 1920)
        self.assertEqual(set(keys.values()), {1})
        self.assertEqual(
            Counter((r["model"], r["arm"]) for r in self.plan),
            {(m, a): 120 for m in self.p.MODELS for a in self.p.ARMS},
        )
        self.assertGreater(len({r["model"] for r in self.plan[:32]}), 1)
        for offset in range(0, len(self.plan), 4):
            block = self.plan[offset : offset + 4]
            self.assertEqual(len({(r["model"], r["case"], r["repetition"]) for r in block}), 1)
            self.assertEqual({r["arm"] for r in block}, set(self.p.ARMS))
        for record in self.plan:
            request = record["request"]
            self.assertEqual(request["reasoning"], {"effort": "medium"})
            self.assertEqual(request["text"], {"verbosity": "medium"})
            self.assertEqual(request["max_output_tokens"], 1024)
            self.assertEqual(request["prompt_cache_options"], self.p.CACHE)
            self.assertIs(request["instructions"], None) if record["arm"] == "baseline" else None
            self.assertEqual(record["request_sha256"], self.p.digest(self.p.encoded(request)))

    def test_generation_then_blind_judges_share_serial_ledger_and_raw_evidence(self):
        summary = self.run_campaign()
        self.assertEqual(len(self.calls), 8)
        self.assertEqual([r["max_output_tokens"] for r in self.calls], [1024] * 4 + [768] * 4)
        self.assertEqual(summary["generation_completed"], 4)
        self.assertEqual(summary["judgment_valid"], 4)
        self.assertEqual(summary["outstanding_micros"], 0)
        self.assertEqual(summary["settled_micros"], 8 * 858)
        plan = json.loads((self.output / "judge-plan.json").read_text())
        self.assertEqual(len({r["blind_id"] for r in plan}), 4)
        for record in plan:
            body = self.p.encoded(record["request"])
            for arm in self.p.ARMS:
                self.assertNotIn(('"' + arm + '"').encode(), body)
            for model in self.p.MODELS[1:]:
                self.assertNotIn(model.encode(), body)
        for terminal in summary["terminals"]:
            raw = (self.output / terminal["raw_path"]).read_bytes()
            self.assertEqual(self.p.digest(raw), terminal["raw_sha256"])
        report = self.c.build_report(self.small_plan(), summary)
        self.assertTrue(report["paired_comparisons_available"])
        self.assertEqual(report["models"][self.p.MODELS[0]]["primary"]["paired"], 1)

    def test_known_incomplete_and_blank_outputs_settle_and_continue(self):
        def transport(body, key):
            status, reqid, raw = self.transport(body, key)
            response = json.loads(raw)
            if len(self.calls) == 1:
                response["status"] = "incomplete"
            elif len(self.calls) == 2:
                response["output"] = []
            return status, reqid, self.p.encoded(response)

        summary = self.run_campaign(transport)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(summary["generation_completed"], 2)
        self.assertEqual(summary["generation_failed"], 2)
        self.assertEqual(summary["judgment_valid"], 2)
        self.assertEqual(summary["settled_micros"], 6 * 858)
        self.assertEqual(summary["outstanding_micros"], 0)

    def test_hard_fail_is_judged_and_excluded_from_paired_brevity(self):
        plan = self.small_plan()
        target = next(i for i, r in enumerate(plan, 1) if r["arm"] == "if")

        def transport(body, key):
            status, reqid, raw = self.transport(body, key)
            response = json.loads(raw)
            if len(self.calls) == target:
                response["output"][0]["content"][0]["text"] = "wrong"
            return status, reqid, self.p.encoded(response)

        summary = self.run_campaign(transport)
        self.assertEqual(summary["judgment_valid"], 4)
        report = self.c.build_report(plan, summary)
        primary = report["models"][self.p.MODELS[0]]["primary"]
        self.assertEqual(primary["paired"], 0)
        self.assertEqual(primary["excluded"], 1)
        self.assertIsNone(primary["concise_minus_if"])

    def test_uncertain_accounting_or_http_aborts_all_retaining_reservation(self):
        for mutation in ("usage", "model", "tier", "cache", "http", "transport", "secret"):
            with self.subTest(mutation=mutation):
                self.output = self.base / mutation
                self.calls.clear()

                def transport(body, key, mutation=mutation):
                    status, reqid, raw = self.transport(body, key)
                    response = json.loads(raw)
                    if mutation == "usage":
                        response.pop("usage")
                    if mutation == "model":
                        response["model"] = "wrong"
                    if mutation == "tier":
                        response["service_tier"] = "priority"
                    if mutation == "cache":
                        response.pop("prompt_cache_options")
                    if mutation == "http":
                        status = 401
                    if mutation == "transport":
                        raise TimeoutError(KEY)
                    if mutation == "secret":
                        return 200, KEY, ('{"echo":"' + KEY + '"}').encode()
                    return status, reqid, self.p.encoded(response)

                summary = self.run_campaign(transport)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(summary["settled_micros"], 0)
                self.assertGreater(summary["outstanding_micros"], 0)
                self.assertFalse(
                    self.c.build_report(self.small_plan(), summary)["paired_comparisons_available"]
                )
                self.assertNotIn(KEY, json.dumps(summary))

    def test_invalid_judgment_settles_continues_and_suppresses_all_pairs(self):
        def parse(text, case, blind_id):
            if len(self.calls) == 5:
                raise self.p.Stop("invalid_judgment")
            return {"semantic_pass": True}

        self.output.mkdir()
        (self.output / "responses").mkdir()
        with (
            patch.object(self.c.protocol, "hard_checks", return_value={"hard_pass": True}),
            patch.object(self.c.protocol, "judge_request", side_effect=self.judge_request),
            patch.object(self.c.protocol, "parse_judgment", side_effect=parse),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            summary = self.c.execute(
                self.output, self.small_plan(), self.cases, KEY, self.transport
            )
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(summary["judgment_invalid"], 1)
        self.assertEqual(summary["judgment_valid"], 3)
        self.assertEqual(summary["settled_micros"], 8 * 858)
        self.assertFalse(
            self.c.build_report(self.small_plan(), summary)["paired_comparisons_available"]
        )

    def test_real_protocol_integration_uses_valid_opaque_ids(self):
        self.output.mkdir()
        (self.output / "responses").mkdir()

        def transport(body, key):
            status, request_id, raw = self.transport(body, key)
            request = json.loads(body)
            if request["max_output_tokens"] == 768:
                data = json.loads(request["input"])
                self.assertEqual(
                    set(data),
                    {
                        "blind_id",
                        "prompt",
                        "locale",
                        "rubric",
                        "material_warning_requirement",
                        "material_warning_severity",
                        "candidate_response",
                    },
                )
                value = {
                    "blind_id": data["blind_id"],
                    "rubric_items": [{"item_index": 0, "passed": True, "evidence": "valid answer"}],
                    "material_warning": None,
                    "material_contradiction": False,
                    "contradiction_evidence": None,
                    "semantic_pass": True,
                }
                raw = self.p.encoded(self.response(request, json.dumps(value)))
            return status, request_id, raw

        with contextlib.redirect_stdout(io.StringIO()):
            summary = self.c.execute(self.output, self.small_plan(), self.cases, KEY, transport)
        self.assertIsNone(summary["stop_reason"])
        self.assertEqual(summary["judgment_valid"], 4)

    def test_malformed_unicode_candidate_settles_and_preserves_partial_results(self):
        def transport(body, key):
            status, request_id, raw = self.transport(body, key)
            value = json.loads(raw)
            if len(self.calls) == 1:
                value["output"][0]["content"][0]["text"] = "\ud800"
            return status, request_id, json.dumps(value, ensure_ascii=True).encode()

        summary = self.run_campaign(transport)
        self.assertEqual(summary["generation_failed"], 1)
        self.assertEqual(summary["terminals"][0]["error"], "invalid_output_unicode")
        self.assertEqual(summary["settled_micros"], 7 * 858)
        self.assertEqual(len(self.calls), 7)

    def test_snapshot_freezes_sentence_counter_and_rejects_changed_cases(self):
        sources = self.c.snapshot(ROOT)
        self.assertIn("sentences.py", set(sources))
        self.assertEqual(self.p.digest(sources["response-cases.yaml"]), self.c.protocol.CASE_SHA256)
        original = Path.read_bytes

        def read(path):
            raw = original(path)
            return raw + b"\n" if path == ROOT / "evals/exploratory/response-cases.yaml" else raw

        with (
            patch.object(Path, "read_bytes", read),
            self.assertRaisesRegex(self.p.Stop, "case_pin_mismatch"),
        ):
            self.c.snapshot(ROOT)

    def test_primary_means_use_exact_pairs_and_concise_minus_if_direction(self):
        plan = self.small_plan()

        def transport(body, key):
            status, request_id, raw = self.transport(body, key)
            value = json.loads(raw)
            if len(self.calls) <= 4:
                arm = plan[len(self.calls) - 1]["arm"]
                tokens, answer = (30, "abcdef") if arm == "concise" else (20, "Я🙂")
                value["usage"].update(output_tokens=tokens, total_tokens=100 + tokens)
                value["output"][0]["content"][0]["text"] = answer
            return status, request_id, self.p.encoded(value)

        summary = self.run_campaign(transport)
        report = self.c.build_report(plan, summary)
        primary = report["models"][self.p.MODELS[0]]["primary"]
        self.assertEqual(
            primary["concise_minus_if"],
            {"billed_output_tokens": 10, "nonreasoning_output_tokens": 10, "output_characters": 4},
        )
        self.assertEqual(primary["means"]["if"]["output_characters"], 2)

    def test_semantic_evidence_with_invalid_unicode_is_settled_invalid(self):
        self.output.mkdir()
        (self.output / "responses").mkdir()

        def transport(body, key):
            status, request_id, raw = self.transport(body, key)
            request = json.loads(body)
            if request["max_output_tokens"] == 768:
                data = json.loads(request["input"])
                value = {
                    "blind_id": data["blind_id"],
                    "rubric_items": [{"item_index": 0, "passed": True, "evidence": "\ud800"}],
                    "material_warning": None,
                    "material_contradiction": False,
                    "contradiction_evidence": None,
                    "semantic_pass": True,
                }
                raw = self.p.encoded(self.response(request, json.dumps(value)))
            return status, request_id, raw

        with contextlib.redirect_stdout(io.StringIO()):
            summary = self.c.execute(self.output, self.small_plan(), self.cases, KEY, transport)
        self.assertEqual(summary["judgment_invalid"], 4)
        self.assertEqual(summary["settled_micros"], 8 * 858)
        self.assertNotIn("judgment", summary["terminals"][-1])

    def test_main_preserves_reports_after_provider_abort(self):
        args = [
            "--live",
            "--output",
            str(self.output),
            "--revision",
            REVISION,
            "--confirm-cost",
            "75",
        ]

        def transport(body, key):
            self.transport(body, key)
            return 401, "req_auth", b'{"error":"synthetic auth failure"}'

        with patch.dict(os.environ, ENV, clear=True), contextlib.redirect_stdout(io.StringIO()):
            result = self.c.main(args, root=ROOT, transport=transport, today=dt.date(2026, 9, 18))
        self.assertEqual(result, 1)
        summary = json.loads((self.output / "summary.json").read_text())
        report = json.loads((self.output / "report.json").read_text())
        self.assertEqual(summary["stop_reason"], "http_auth")
        self.assertEqual(summary["generation_missing"], 1919)
        self.assertFalse(report["paired_comparisons_available"])
        self.assertEqual(
            report["provenance"]["summary_sha256"],
            self.p.digest((self.output / "summary.json").read_bytes()),
        )
        self.assertEqual(report["provenance"]["ledger_sha256"], summary["ledger_sha256"])

    def test_budget_and_wall_cutoff_prevent_transport(self):
        for name, limit, ticks in (("budget", 1, [0, 0]), ("time", self.c.BUDGET, [0, 20_000])):
            self.output = self.base / name
            with patch.object(self.c, "BUDGET", limit):
                summary = self.run_campaign(clock=iter(ticks).__next__)
            self.assertEqual(self.calls, [])
            self.assertIn(summary["stop_reason"], {"budget_exhausted", "wall_clock_cutoff"})
            self.assertTrue((self.output / "judge-plan.json").is_file())

    def test_judging_cannot_bypass_generation_spending(self):
        plan = self.small_plan()
        request = self.judge_request(self.cases[0], "valid answer", "a" * 32)
        reservation = self.c.request_record(request)["reservation_micros"]

        def transport(body, key):
            status, request_id, raw = self.transport(body, key)
            value = json.loads(raw)
            value["usage"].update(input_tokens=10_000, output_tokens=500, total_tokens=10_500)
            return status, request_id, self.p.encoded(value)

        generation_cost = 49_958
        # At most four generation settlements fit before the first judge reservation.
        cap = 4 * generation_cost + reservation - 1
        self.assertGreaterEqual(
            cap, max(r["reservation_micros"] for r in plan) + 3 * generation_cost
        )
        with patch.object(self.c, "BUDGET", cap):
            summary = self.run_campaign(transport)
        self.assertTrue(summary["generation_campaign_complete"])
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(summary["stop_reason"], "budget_exhausted")
        self.assertEqual(summary["settled_micros"], 4 * generation_cost)
        self.assertEqual(summary["judgment_missing"], 4)
        self.assertFalse(self.c.build_report(plan, summary)["paired_comparisons_available"])

    def test_dry_run_snapshots_provenance_without_key_or_transport(self):
        args = ["--dry-run", "--output", str(self.output), "--revision", REVISION]

        def environment(name, default=None):
            self.assertIn(name, {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "COLUMNS", "LINES"})
            return default

        with (
            patch.object(os.environ, "get", side_effect=environment),
            patch.object(
                self.c,
                "snapshot",
                return_value={**self.sources, "response-cases.yaml": b"synthetic cases"},
            ),
            patch.object(self.c.protocol, "load_cases", return_value=self.cases),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(self.c.main(args, root=ROOT, transport=self.transport), 0)
        self.assertEqual(self.calls, [])
        for name in (
            "manifest.json",
            "prices.json",
            "generation-plan.json",
            "ledger.jsonl",
            "judge-plan.json",
            "summary.json",
            "report.json",
            "report.md",
        ):
            self.assertTrue((self.output / name).is_file(), name)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(manifest["format"], "exploratory-comparison-v1")
        self.assertEqual(manifest["revision"], REVISION)
        self.assertEqual(manifest["planned"], 1920)
        self.assertIn("PyYAML", manifest["dependencies"])
        self.assertIn("created_at", manifest)
        self.assertEqual(
            manifest["prices_sha256"], self.p.digest((self.output / "prices.json").read_bytes())
        )

    def test_live_context_price_revision_and_existing_output_gates(self):
        args = [
            "--live",
            "--output",
            str(self.output),
            "--revision",
            REVISION,
            "--confirm-cost",
            "75",
        ]
        for environment in (
            {},
            {**ENV, "GITHUB_REF": "refs/heads/topic"},
            {**ENV, "GITHUB_RUN_ATTEMPT": "2"},
            {**ENV, "OPENAI_API_KEY": ""},
        ):
            with (
                patch.dict(os.environ, environment, clear=True),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(self.c.main(args, root=ROOT, transport=self.transport), 1)
            self.assertEqual(self.calls, [])
        with patch.dict(os.environ, ENV, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                self.c.main(args, root=ROOT, transport=self.transport, today=dt.date(2026, 9, 26)),
                1,
            )
        self.output.mkdir()
        with patch.dict(os.environ, ENV, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                self.c.main(args, root=ROOT, transport=self.transport, today=dt.date(2026, 9, 18)),
                1,
            )
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
