"""Offline, direct-runnable tests; no repository fixture discovery or provider calls."""

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
SCRIPT = ROOT / "tools" / "exploratory_pilot.py"
REVISION = "1" * 40
KEY = "offline-sentinel-credential-1234567890"
ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_RUN_ATTEMPT": "1",
    "OPENAI_API_KEY": KEY,
}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "standalone exploratory pilot launcher is missing")
        spec = importlib.util.spec_from_file_location("exploratory_pilot", SCRIPT)
        self.p = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.p)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / "run"
        self.environment = patch.dict(os.environ, ENV, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.calls = []

    def argv(self, live=True):
        return [
            "--live" if live else "--dry-run",
            "--output",
            str(self.output),
            "--revision",
            REVISION,
        ] + (["--confirm-cost", "5"] if live else [])

    def response(self, request):
        return {
            "model": request["model"],
            "status": "completed",
            "error": None,
            "service_tier": "default",
            "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
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
                    "content": [
                        {"type": "output_text", "text": "v2.4.1 8080 https://api.example.com/v1"}
                    ],
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
        return 200, "req_offline", self.p.encoded(self.response(request))

    def run_pilot(self, transport=None, live=True, root=ROOT, date=dt.date(2026, 9, 18)):
        with contextlib.redirect_stderr(io.StringIO()):
            return self.p.main(
                self.argv(live), root=root, transport=transport or self.transport, today=date
            )

    def summary(self):
        return json.loads((self.output / "summary.json").read_text())

    def nonsecret_environment(self, name, default=None):
        self.assertIn(name, {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "COLUMNS", "LINES"})
        return default

    def stop_with(self, mutate=None, status=200, raw=None):
        def transport(body, key):
            _, request_id, good = self.transport(body, key)
            response = json.loads(good)
            if mutate:
                mutate(response)
            return status, request_id, raw if raw is not None else self.p.encoded(response)

        self.assertEqual(self.run_pilot(transport), 1)
        summary = self.summary()
        self.assertEqual(
            (summary["completed"], summary["failed"], summary["not_attempted"]), (0, 1, 31)
        )
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(summary["settled_micros"], 0)
        self.assertGreater(summary["outstanding_micros"], 0)
        return summary

    def test_plan_has_32_matched_fixed_requests(self):
        plan = self.p.build_plan(self.p.snapshot(ROOT))
        self.assertEqual(len(plan), 32)
        self.assertEqual(
            Counter(record["model"] for record in plan), dict.fromkeys(self.p.MODELS, 8)
        )
        pairs = Counter((r["model"], r["case"], r["arm"], r["repetition"]) for r in plan)
        self.assertEqual(len(pairs), 32)
        self.assertEqual(set(pairs.values()), {1})
        self.assertEqual(plan, self.p.build_plan(self.p.snapshot(ROOT)))
        self.assertGreater(sum(r["reservation_micros"] for r in plan), self.p.BUDGET)
        for record in plan:
            request = record["request"]
            self.assertEqual(
                set(request),
                {
                    "model",
                    "instructions",
                    "input",
                    "store",
                    "tools",
                    "max_output_tokens",
                    "reasoning",
                    "text",
                    "service_tier",
                    "prompt_cache_options",
                },
            )
            self.assertEqual(request["tools"], [])
            self.assertIs(request["store"], False)
            self.assertEqual(request["reasoning"], {"effort": "medium"})
            self.assertEqual(request["text"], {"verbosity": "medium"})
            self.assertEqual(request["service_tier"], "default")
            self.assertEqual(request["max_output_tokens"], 1024)
            self.assertEqual(request["prompt_cache_options"], {"mode": "explicit", "ttl": "30m"})
            self.assertEqual(record["request_sha256"], self.p.digest(self.p.encoded(request)))
            self.assertLessEqual(record["input_bound"], 272_000)

    def test_dry_run_never_reads_environment_or_creates_network_client(self):
        with (
            patch.object(os.environ, "get", side_effect=self.nonsecret_environment),
            patch.object(
                self.p.http.client, "HTTPSConnection", side_effect=AssertionError("network")
            ),
        ):
            self.assertEqual(self.run_pilot(live=False), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.summary()["not_attempted"], 32)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(manifest["revision"], REVISION)
        for name, digest in manifest["source_sha256"].items():
            self.assertEqual(self.p.digest((self.output / "sources" / name).read_bytes()), digest)

    def test_pin_failure_precedes_key_and_transport(self):
        root = self.base / "repo"
        for relative in self.p.SOURCE_FILES.values():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        (root / "evals/baselines/caveman/SKILL.md").write_bytes(b"tampered")
        with patch.object(os.environ, "get", side_effect=self.nonsecret_environment):
            self.assertEqual(self.run_pilot(root=root), 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.calls, [])

    def test_success_accounts_all_buckets_and_persists_raw_before_settlement(self):
        original_account = self.p.account

        def account(response, record):
            raw = self.output / "responses" / f"{record['index']:04d}.bin"
            self.assertEqual(json.loads(raw.read_bytes()), response)
            return original_account(response, record)

        with patch.object(self.p, "account", side_effect=account):
            self.assertEqual(self.run_pilot(), 0)
        summary = self.summary()
        self.assertEqual(
            (summary["completed"], summary["failed"], summary["hard_pass"]), (32, 0, 32)
        )
        self.assertEqual(summary["outstanding_micros"], 0)
        first = summary["terminals"][0]
        self.assertEqual(first["settled_micros"], 858)
        self.assertEqual(
            first["usage"],
            {
                "input_tokens": 100,
                "output_tokens": 25,
                "total_tokens": 125,
                "cached_tokens": 20,
                "cache_write_tokens": 30,
                "reasoning_tokens": 10,
                "ordinary_input_tokens": 50,
                "nonreasoning_output_tokens": 15,
            },
        )

    def test_quality_failure_does_not_change_accounting(self):
        original = self.response

        def response(request):
            value = original(request)
            value["output"][0]["content"][0]["text"] = "wrong answer"
            return value

        self.response = response
        self.assertEqual(self.run_pilot(), 0)
        summary = self.summary()
        self.assertEqual(
            (summary["completed"], summary["hard_pass"], summary["hard_fail"]), (32, 0, 32)
        )
        self.assertEqual(summary["terminals"][0]["settled_micros"], 858)
        self.assertEqual(
            summary["terminals"][0]["quality"]["missing_literals"], list(self.p.LITERALS)
        )

    def test_missing_and_invalid_usage_never_becomes_zero_cost(self):
        mutations = [
            lambda r: r.pop("usage"),
            lambda r: r["usage"].pop("input_tokens"),
            lambda r: r["usage"]["input_tokens_details"].pop("cached_tokens"),
            lambda r: r["usage"]["input_tokens_details"].pop("cache_write_tokens"),
            lambda r: r["usage"]["output_tokens_details"].pop("reasoning_tokens"),
            lambda r: r["usage"].update(input_tokens=True),
            lambda r: r["usage"].update(input_tokens=100.0),
            lambda r: r["usage"].update(input_tokens=-1),
            lambda r: r["usage"].update(output_tokens=1025, total_tokens=1125),
            lambda r: r["usage"].update(total_tokens=126),
            lambda r: r["usage"]["input_tokens_details"].update(cache_write_tokens=81),
            lambda r: r["usage"]["output_tokens_details"].update(reasoning_tokens=26),
            lambda r: r["usage"].update(input_tokens=300_000, total_tokens=300_025),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.output = self.base / f"usage-{index}"
                self.calls.clear()
                self.stop_with(mutate)
                self.assertTrue((self.output / "responses" / "0001.bin").is_file())

    def test_response_contract_mismatch_stops(self):
        mutations = [
            lambda r: r.update(model="another-model"),
            lambda r: r.update(status="incomplete"),
            lambda r: r.update(error={"message": "provider text"}),
            lambda r: r.update(service_tier="priority"),
            lambda r: r.pop("prompt_cache_options"),
            lambda r: r.update(prompt_cache_options={"mode": "implicit", "ttl": "30m"}),
            lambda r: r.update(output=[]),
            lambda r: r["output"][0]["content"][0].update(text="  "),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.output = self.base / f"response-{index}"
                self.calls.clear()
                summary = self.stop_with(mutate)
                self.assertEqual(summary["unknown"], 1)
                self.assertEqual(summary["terminals"][0]["requested_model"], "gpt-5.6-sol")

    def test_http_auth_rate_limit_and_redirect_never_retry(self):
        for status in (401, 403, 429, 500, 302):
            with self.subTest(status=status):
                self.output = self.base / f"http-{status}"
                self.calls.clear()
                summary = self.stop_with(status=status, raw=b'{"error":"opaque"}')
                self.assertEqual(summary["terminals"][0]["http_status"], status)
                self.assertEqual(
                    (self.output / "responses" / "0001.bin").read_bytes(), b'{"error":"opaque"}'
                )

    def test_transport_timeout_and_exception_stop_without_message_leak(self):
        for index, error in enumerate((TimeoutError(KEY), RuntimeError(KEY))):
            self.output = self.base / f"transport-{index}"
            self.calls.clear()

            def transport(body, key, error=error):
                self.transport(body, key)
                raise error

            self.assertEqual(self.run_pilot(transport), 1)
            self.assertEqual(len(self.calls), 1)
            self.assertGreater(self.summary()["outstanding_micros"], 0)
            for artifact in self.output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn(KEY.encode(), artifact.read_bytes())

    def test_insufficient_budget_prevents_dispatch(self):
        with patch.object(self.p, "BUDGET", 1):
            self.assertEqual(self.run_pilot(), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.summary()["not_attempted"], 32)
        self.assertEqual(self.summary()["stop_reason"], "budget_exhausted")

    def test_existing_output_and_symlink_are_rejected(self):
        for symlink in (False, True):
            target = self.base / f"existing-{symlink}"
            target.mkdir()
            marker = target / "keep"
            marker.write_bytes(b"original")
            self.output = self.base / f"link-{symlink}" if symlink else target
            if symlink:
                self.output.symlink_to(target, target_is_directory=True)
            self.assertEqual(self.run_pilot(), 1)
            self.assertEqual(marker.read_bytes(), b"original")
        self.assertEqual(self.calls, [])

    def test_raw_malformed_duplicate_and_nonfinite_are_preserved(self):
        for index, raw in enumerate((b"{broken", b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}')):
            self.output = self.base / f"json-{index}"
            self.calls.clear()
            self.stop_with(raw=raw)
            self.assertEqual((self.output / "responses" / "0001.bin").read_bytes(), raw)

    def test_oversized_raw_keeps_bounded_prefix_and_stops(self):
        raw = b"x" * (self.p.RAW_LIMIT + 20)
        summary = self.stop_with(raw=raw)
        self.assertTrue(summary["terminals"][0]["truncated"])
        self.assertEqual(
            (self.output / "responses" / "0001.bin").read_bytes(), raw[: self.p.RAW_LIMIT]
        )

    def test_credential_echo_withholds_body_and_safe_request_id(self):
        summary = self.stop_with(raw=('{"echo":"' + KEY + '"}').encode())
        self.assertTrue(summary["terminals"][0]["body_withheld"])
        self.assertEqual(list((self.output / "responses").iterdir()), [])
        for artifact in self.output.rglob("*"):
            if artifact.is_file():
                self.assertNotIn(KEY.encode(), artifact.read_bytes())

    def test_json_escaped_credentials_are_withheld_before_raw_persistence(self):
        escaped_keys = (
            KEY.replace("o", "\\u006f", 1),
            "".join(f"\\u{ord(char):04x}" for char in KEY),
        )
        for status in (200, 401):
            for index, escaped_key in enumerate(escaped_keys):
                with self.subTest(status=status, encoding=index):
                    self.output = self.base / f"escaped-{status}-{index}"
                    self.calls.clear()
                    response = self.response({"model": "gpt-5.6-sol"})
                    response["output"][0]["content"][0]["text"] = KEY
                    if status == 401:
                        response = {"error": {"message": KEY}}
                    raw = self.p.encoded(response).replace(KEY.encode(), escaped_key.encode())
                    self.assertNotIn(KEY.encode(), raw)
                    summary = self.stop_with(status=status, raw=raw)
                    self.assertTrue(summary["terminals"][0]["body_withheld"])
                    self.assertEqual(list((self.output / "responses").iterdir()), [])

    def test_escaped_credential_in_truncated_json_string_is_withheld(self):
        escaped = "".join(f"\\u{ord(char):04x}" for char in KEY).encode()
        raw = b'{"echo":"' + escaped + b"x" * self.p.RAW_LIMIT
        summary = self.stop_with(raw=raw)
        self.assertTrue(summary["terminals"][0]["body_withheld"])
        self.assertEqual(list((self.output / "responses").iterdir()), [])

    def test_truncated_unicode_escape_after_credential_is_withheld(self):
        prefix = b'{"echo":"' + "".join(f"\\u{ord(char):04x}" for char in KEY).encode()
        limit = self.p.RAW_LIMIT + 6 * len(KEY) + 1
        raw = prefix + b"x" * (limit - len(prefix) - 3) + b'\\u006f"}'
        summary = self.stop_with(raw=raw)
        self.assertTrue(summary["terminals"][0].get("body_withheld"))
        self.assertEqual(list((self.output / "responses").iterdir()), [])

    def test_partial_or_malformed_escape_cannot_hide_an_earlier_credential(self):
        prefix = b'{"echo":"' + "".join(f"\\u{ord(char):04x}" for char in KEY).encode()
        limit = self.p.response_read_limit(KEY)
        bodies = (
            prefix + b"x" * (limit - len(prefix) - 4) + b'\\u0078"}',
            prefix + b"x" * (limit - len(prefix) - 1) + b'\\\\"}',
            prefix + b'\\q"}',
        )
        for index, raw in enumerate(bodies):
            with self.subTest(index=index):
                self.output = self.base / f"malformed-tail-{index}"
                self.calls.clear()
                summary = self.stop_with(raw=raw)
                self.assertTrue(summary["terminals"][0].get("body_withheld"))
                self.assertEqual(list((self.output / "responses").iterdir()), [])

    def test_credential_screen_matches_json_escapes_but_not_letter_case_changes(self):
        special_key = 'offline"\\/key'
        escaped = json.dumps(special_key).replace("/", "\\/").encode()
        self.assertTrue(self.p.credential_echo(escaped, special_key))
        unicode_escaped = "".join(f"\\u{ord(char):04X}" for char in KEY).encode()
        self.assertTrue(self.p.credential_echo(unicode_escaped, KEY))
        self.assertFalse(self.p.credential_echo(KEY.swapcase().encode(), KEY))

    def test_live_requires_workflow_key_confirmation_fresh_prices_and_revision(self):
        for index, env in enumerate(
            (
                {},
                {**ENV, "GITHUB_REF": "refs/heads/topic"},
                {**ENV, "GITHUB_RUN_ATTEMPT": "2"},
                {**ENV, "OPENAI_API_KEY": ""},
            )
        ):
            self.output = self.base / f"context-{index}"
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(self.run_pilot(), 1)
            self.assertFalse(self.output.exists())
        for date in (dt.date(2026, 9, 17), dt.date(2026, 9, 26)):
            self.assertEqual(self.run_pilot(date=date), 1)
        for args in (self.argv()[:-2], [*self.argv(), "--revision", "bad"]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.p.main(args, root=ROOT, transport=self.transport), 1)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.p.main(["--output", str(self.output), "--revision", REVISION], root=ROOT)
        self.assertEqual(self.calls, [])

    def test_transport_is_fixed_host_path_timeout_and_bounded_read(self):
        observed = {}

        class Response:
            status = 200

            def getheader(self, name):
                self_outer.assertEqual(name, "x-request-id")
                return "req_fixed"

            def read(self, count):
                observed["read_limit"] = count
                return b"{}"

        class Connection:
            def __init__(self, host, port, timeout):
                observed.update(host=host, port=port, timeout=timeout)

            def request(self, method, path, body, headers):
                observed.update(method=method, path=path, body=body, headers=headers)

            def getresponse(self):
                return Response()

            def close(self):
                observed["closed"] = True

        self_outer = self
        with patch.object(self.p.http.client, "HTTPSConnection", Connection):
            self.assertEqual(self.p.https_transport(b"{}", KEY), (200, "req_fixed", b"{}"))
        self.assertEqual(
            (observed["host"], observed["port"], observed["timeout"]), ("api.openai.com", 443, 120)
        )
        self.assertEqual((observed["method"], observed["path"]), ("POST", "/v1/responses"))
        self.assertEqual(observed["read_limit"], self.p.RAW_LIMIT + 6 * len(KEY) + 1)
        self.assertTrue(observed["closed"])


if __name__ == "__main__":
    unittest.main()
