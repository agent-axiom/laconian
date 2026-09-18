"""Offline contract checks for the intentionally narrow live pilot workflow."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/benchmark-exploratory.yml"


class ExploratoryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_manual_main_first_attempt_and_explicit_confirmation(self):
        triggers = self.workflow.split("on:\n", 1)[1].split("permissions:", 1)[0]
        self.assertIn("  workflow_dispatch:\n", triggers)
        self.assertIn("        type: boolean\n", triggers)
        self.assertIn("        default: false\n", triggers)
        self.assertNotRegex(triggers, r"(?m)^  (push|pull_request|schedule|workflow_call):")
        for guard in (
            "github.event_name == 'workflow_dispatch'",
            "github.ref == 'refs/heads/main'",
            "github.run_attempt == '1'",
            "inputs.confirm_cost == true",
        ):
            self.assertIn(guard, self.workflow)

    def test_read_only_token_and_serial_runs(self):
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotIn(": write", self.workflow)
        self.assertIn("  group: laconian-exploratory-live\n", self.workflow)
        self.assertIn("  cancel-in-progress: false\n", self.workflow)
        self.assertIn("    environment: benchmark-live\n", self.workflow)
        self.assertIn("    timeout-minutes: 75\n", self.workflow)

    def test_actions_pinned_and_checkout_has_no_credentials(self):
        actions = re.findall(r"uses: (\S+)", self.workflow)
        self.assertEqual(len(actions), 3)
        for action in actions:
            self.assertRegex(action, r"^[\w/-]+@[0-9a-f]{40}$")
        self.assertIn("          ref: ${{ github.sha }}\n", self.workflow)
        self.assertIn("          persist-credentials: false\n", self.workflow)

    def test_preflight_is_offline_and_before_live_step(self):
        offline, live = self.workflow.split("      - name: Run live pilot", 1)
        self.assertIn("python tests/test_exploratory_pilot.py", offline)
        self.assertIn("python tests/test_exploratory_workflow.py", offline)
        self.assertIn("--dry-run", offline)
        self.assertIn('mkdir -p "$RUNNER_TEMP/exploratory-pilot"', offline)
        self.assertNotIn("secrets.", offline)
        self.assertNotRegex(self.workflow, r"\b(pip install|uv sync|npm install)\b")
        self.assertIn("--live", live)

    def test_key_only_in_live_step_and_fixed_cap(self):
        self.assertEqual(self.workflow.count("${{ secrets.OPENAI_API_KEY }}"), 1)
        live = self.workflow.split("      - name: Run live pilot", 1)[1]
        live = live.split("      - name:", 1)[0]
        self.assertIn("        env:\n          OPENAI_API_KEY:", live)
        self.assertIn("--confirm-cost 5", live)
        self.assertIn('--revision "$GITHUB_SHA"', live)
        self.assertIn('--output "$RUNNER_TEMP/exploratory-pilot/live"', live)
        self.assertNotIn("${{ inputs.", live)

    def test_failure_artifacts_retained_without_executing_outputs(self):
        upload = self.workflow.split("      - name: Preserve pilot artifacts", 1)[1]
        self.assertIn("        if: always()\n", upload)
        self.assertIn("actions/upload-artifact@", upload)
        self.assertIn("          path: ${{ runner.temp }}/exploratory-pilot/\n", upload)
        self.assertIn("          retention-days: 90\n", upload)
        self.assertIn("          if-no-files-found: error\n", upload)
        self.assertIn("          include-hidden-files: false\n", upload)
        self.assertIn("          overwrite: false\n", upload)
        self.assertNotIn("GITHUB_STEP_SUMMARY", self.workflow)
        self.assertNotRegex(self.workflow, r"\b(eval|source)\s")


if __name__ == "__main__":
    unittest.main()
