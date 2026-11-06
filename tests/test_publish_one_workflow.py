"""Tests for .github/workflows/publish-one.yml."""
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

    def _on(self):
        return self.data.get("on") or self.data.get(True) or {}

    def test_workflow_yaml_valid(self):
        self.assertIsInstance(self.data, dict)
        jobs = self.data["jobs"]
        for name in ("detect", "publish_foodbanks", "publish_shelters", "publish_warmspaces"):
            self.assertIn(name, jobs)
            self.assertIn("steps", jobs[name])

    def test_inputs_are_layer_and_id_only(self):
        on = self._on()
        self.assertEqual(on["push"]["branches"], ["main"])
        self.assertIn("overrides/**", on["push"]["paths"])
        inputs = on["workflow_dispatch"]["inputs"]
        self.assertEqual(set(inputs), {"layer", "id"})
        self.assertEqual(sorted(inputs["layer"]["options"]), ["foodbanks", "shelters", "warmspaces"])

    def test_each_layer_has_its_own_queue(self):
        """Section 16: the queue is the layer's refresh group, not a filename guess."""
        self.assertNotIn('grep -q "shelter"', self.content)
        self.assertNotIn('grep -q "warmspace"', self.content)
        self.assertNotRegex(self.content, r"grep .*shelter")
        jobs = self.data["jobs"]
        self.assertRegex(
            self.content,
            r"group:\s*\$\{\{\s*github\.ref\s*==\s*'refs/heads/main'\s*&&\s*'refresh'\s*\|\|\s*format\('refresh-pr-\{0\}',\s*github\.ref_name\)\s*\}\}",
        )
        self.assertRegex(
            self.content,
            r"group:\s*\$\{\{\s*github\.ref\s*==\s*'refs/heads/main'\s*&&\s*'refresh-shelters'\s*\|\|\s*format\('refresh-shelters-pr-\{0\}',\s*github\.ref_name\)\s*\}\}",
        )
        self.assertRegex(
            self.content,
            r"group:\s*\$\{\{\s*github\.ref\s*==\s*'refs/heads/main'\s*&&\s*'refresh-warmspaces'\s*\|\|\s*format\('refresh-warmspaces-pr-\{0\}',\s*github\.ref_name\)\s*\}\}",
        )
        for name in ("publish_foodbanks", "publish_shelters", "publish_warmspaces"):
            self.assertEqual(jobs[name]["concurrency"]["cancel-in-progress"], False)
        self.assertEqual(jobs["publish_foodbanks"]["if"], "needs.detect.outputs.run_foodbanks == 'true'")
        self.assertEqual(jobs["publish_shelters"]["if"], "needs.detect.outputs.run_shelters == 'true'")
        self.assertEqual(jobs["publish_warmspaces"]["if"], "needs.detect.outputs.run_warmspaces == 'true'")
        self.assertIn("publish_one.py --commit", self.content)
        self.assertIn("--list", self.content)
        self.assertIn("for iid in ids", self.content)

    def test_practice_cannot_publish_and_guards_a_dirty_worktree(self):
        self.assertIn("--dry-run", self.content)
        self.assertIn("github.ref != 'refs/heads/main'", self.content)
        steps = []
        for job in self.data["jobs"].values():
            steps.extend(job.get("steps") or [])
        commits = [step for step in steps if step.get("id") == "commit"]
        self.assertEqual(len(commits), 3)
        for step in commits:
            self.assertEqual(step.get("if"), "github.ref == 'refs/heads/main'")
        emails = [step for step in steps if "new_live_email.py" in str(step.get("run", ""))]
        self.assertEqual(len(emails), 3)
        for step in emails:
            self.assertIn("github.ref == 'refs/heads/main'", step.get("if", ""))
            self.assertIn("steps.commit.outcome == 'success'", step.get("if", ""))
            self.assertIn("--baseline", step["run"])
            self.assertIn("--send", step["run"])
        self.assertIn("BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}", self.content)
        self.assertIn("PRACTICE: Brevo skipped", self.content)
        self.assertIn("PRACTICE: commit skipped", self.content)
        self.assertIn("name: Practice-run guard", self.content)
        self.assertIn("if: always() && github.ref != 'refs/heads/main'", self.content)
        self.assertIn("git diff --quiet", self.content)
        self.assertIn("git diff --cached --quiet", self.content)
        self.assertIn("git status --porcelain", self.content)
        self.assertIn("LIVE_BASELINE", self.content)
        self.assertGreaterEqual(len(re.findall(r"git diff --quiet", self.content)), 3)

    def test_workflow_does_not_rebuild_a_layer(self):
        for banned in ("build.py", "build_shelters.py", "build_warmspaces.py", "full_check.py", "build_seo.py"):
            self.assertNotIn(banned, self.content)
        self.assertIn("python scripts/publish_one.py", self.content)


if __name__ == "__main__":
    unittest.main()
