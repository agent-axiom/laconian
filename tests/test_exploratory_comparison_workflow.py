"""Credential-free checks of the manual comparison workflow contract."""

import re
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / ".github/workflows/benchmark-comparison.yml"


class ComparisonWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = PATH.read_text()

    def test_manual_main_first_attempt_confirmed(self):
        trigger = self.text.split("on:\n", 1)[1].split("permissions:", 1)[0]
        self.assertIn("  workflow_dispatch:\n", trigger)
        self.assertIn("        default: false", trigger)
        self.assertNotRegex(trigger, r"(?m)^  (push|schedule|pull_request|workflow_call):")
        for guard in (
            "github.event_name == 'workflow_dispatch'",
            "github.ref == 'refs/heads/main'",
            "github.run_attempt == '1'",
            "inputs.confirm_cost == true",
        ):
            self.assertIn(guard, self.text)

    def test_readonly_pinned_and_serial(self):
        self.assertIn("permissions:\n  contents: read\n", self.text)
        self.assertNotIn(": write", self.text)
        self.assertIn("  group: laconian-exploratory-live\n", self.text)
        self.assertIn("  cancel-in-progress: false\n", self.text)
        self.assertIn("    timeout-minutes: 350\n", self.text)
        self.assertIn("    environment: benchmark-live\n", self.text)
        self.assertIn("          persist-credentials: false\n", self.text)
        self.assertIn("          ref: ${{ github.sha }}\n", self.text)
        actions = re.findall(r"uses: (\S+)", self.text)
        self.assertEqual(len(actions), 4)
        for action in actions:
            self.assertRegex(action, r"^[\w/-]+@[0-9a-f]{40}$")

    def test_secret_only_live_after_locked_offline_preflight(self):
        before, after = self.text.split("      - name: Run live comparison", 1)
        live = after.split("      - name:", 1)[0]
        self.assertIn("uv sync --all-extras --locked", before)
        self.assertIn('UV_OFFLINE: "1"', live)
        self.assertIn("--dry-run", before)
        self.assertIn("tests/test_exploratory_protocol.py", before)
        self.assertIn("tests/test_exploratory_comparison.py", before)
        self.assertNotIn("secrets.", before)
        self.assertEqual(self.text.count("${{ secrets.OPENAI_API_KEY }}"), 1)
        self.assertIn("--live --confirm-cost 75", live)
        self.assertIn('--revision "$GITHUB_SHA"', live)
        self.assertIn('--output "$RUNNER_TEMP/exploratory-comparison/live"', live)
        self.assertNotIn("${{ inputs.", live)

    def test_artifacts_even_failure_without_model_execution(self):
        upload = self.text.split("      - name: Preserve comparison artifacts", 1)[1]
        for expected in (
            "if: always()",
            "overwrite: false",
            "retention-days: 90",
            "include-hidden-files: false",
            "if-no-files-found: error",
        ):
            self.assertIn(expected, upload)
        self.assertIn("path: ${{ runner.temp }}/exploratory-comparison/", upload)
        self.assertNotRegex(self.text, r"\b(eval|source)\s")
        self.assertNotIn("GITHUB_STEP_SUMMARY", self.text)


if __name__ == "__main__":
    unittest.main()
