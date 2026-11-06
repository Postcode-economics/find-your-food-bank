"""Tests for .github/workflows/publish-one.yml:
Asserts concurrency groups, github.ref guards, inputs, and that practice cannot publish.
"""
import os
import re
import subprocess
import sys
import unittest

try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "publish-one.yml")


class PublishOneWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.content = f.read()
        cls.data = yaml.safe_load(cls.content)

    def test_workflow_yaml_valid(self):
        """Workflow must be valid YAML that loads into a dict with jobs."""
        self.assertIsInstance(self.data, dict)
        self.assertIn("jobs", self.data)
        self.assertIn("publish_one", self.data["jobs"])
        self.assertIn("steps", self.data["jobs"]["publish_one"])

    def test_workflow_triggers_and_inputs(self):
        """Must support push to main for overrides/** and workflow_dispatch with layer and id inputs."""
        on_trigger = self.data.get("on") or {}
        self.assertIn("push", on_trigger)
        self.assertEqual(on_trigger["push"]["branches"], ["main"])
        self.assertIn("overrides/**", on_trigger["push"]["paths"])

        self.assertIn("workflow_dispatch", on_trigger)
        inputs = on_trigger["workflow_dispatch"].get("inputs") or {}
        self.assertIn("layer", inputs)
        self.assertIn("id", inputs)
        self.assertEqual(sorted(inputs["layer"]["options"]), ["foodbanks", "shelters", "warmspaces"])

    def test_concurrency_group(self):
        """Concurrency group must match section 16:
        - foodbanks: 'refresh' on main, 'refresh-pr-<branch>' off main
        - shelters: 'refresh-shelters' on main, 'refresh-shelters-pr-<branch>' off main
        - warmspaces: 'refresh-warmspaces' on main, 'refresh-warmspaces-pr-<branch>' off main
        cancel-in-progress: false
        """
        self.assertIn("refresh", self.content)
        self.assertIn("refresh-shelters", self.content)
        self.assertIn("refresh-warmspaces", self.content)
        self.assertIn("refresh-pr-", self.content)
        self.assertIn("refresh-shelters-pr-", self.content)
        self.assertIn("refresh-warmspaces-pr-", self.content)
        self.assertEqual(self.data["jobs"]["publish_one"].get("concurrency", {}).get("cancel-in-progress"), False)

    def test_gh_token_is_ref_conditional(self):
        """GH_TOKEN must be empty on non-main refs."""
        gh_token_lines = [line.strip() for line in self.content.splitlines() if "GH_TOKEN:" in line]
        self.assertTrue(len(gh_token_lines) >= 1)
        expected = "GH_TOKEN: ${{ github.ref == 'refs/heads/main' && github.token || '' }}"
        for line in gh_token_lines:
            self.assertEqual(line, expected)

    def test_publishing_steps_run_only_on_main(self):
        """Commit and email steps must be guarded with github.ref == 'refs/heads/main'."""
        steps = self.data["jobs"]["publish_one"]["steps"]
        commit_step = [s for s in steps if s.get("id") == "commit"][0]
        self.assertEqual(commit_step.get("if"), "github.ref == 'refs/heads/main'")

        email_steps = [s for s in steps if "new_live_email.py" in str(s.get("run", ""))]
        self.assertTrue(len(email_steps) >= 1)
        self.assertIn("github.ref == 'refs/heads/main'", email_steps[0].get("if", ""))
        self.assertIn("steps.commit.outcome == 'success'", email_steps[0].get("if", ""))

    def test_practice_skip_echoes_present(self):
        """On non-main refs, skipped steps echo fixed lines."""
        self.assertIn("PRACTICE: Brevo skipped", self.content)
        self.assertIn("PRACTICE: commit skipped", self.content)

    def test_brevo_api_key_secret_wired(self):
        """Keep BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }} wired."""
        self.assertIn("BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}", self.content)

    def test_practice_run_guard(self):
        """A final step runs only on non-main refs, fails if anything is staged or HEAD differs from baseline."""
        self.assertIn("name: Practice-run guard", self.content)
        self.assertIn("if: always() && github.ref != 'refs/heads/main'", self.content)
        self.assertIn("git diff --cached --quiet", self.content)
        self.assertIn("LIVE_BASELINE", self.content)


if __name__ == "__main__":
    unittest.main()
