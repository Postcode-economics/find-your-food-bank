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

    def test_commit_stages_phone_baseline(self):
        self.assertGreaterEqual(self.content.count("git add overrides/phone_baseline.json"), 3)

    def test_every_publish_commit_retags_index_html(self):
        """7 Nov 2026: publish commits changed data.js / stamp.js but not their ?v= tags in index.html (rule 38).
        Each layer's commit must stage index.html and re-tag it after a rebase and on a stamp.js conflict."""
        for f in ("data.full.js data.js", "shelters.js", "warmspaces.js"):
            self.assertIn("git add %s stamp.js index.html" % f, self.content)
        self.assertEqual(self.content.count("git pull --rebase --autostash && python scripts/seo_meta.py --index-assets"), 3)
        self.assertEqual(self.content.count("git add stamp.js index.html"), 3)

    def test_workflow_does_not_rebuild_a_layer(self):
        for banned in ("build.py", "build_shelters.py", "build_warmspaces.py", "full_check.py", "build_seo.py"):
            self.assertNotIn(banned, self.content)
        self.assertIn("python scripts/publish_one.py", self.content)


    def test_lock_checks_run_before_anything_is_published(self):
        """9 Nov 2026: a fast-track card changed what a lock test expected and every refresh then failed.
        Each layer runs the refreshes' own checks on the card it is about to publish, after the publish
        step and before the commit, with no always() so a failure stops the commit and the email."""
        for name in ("publish_foodbanks", "publish_shelters", "publish_warmspaces"):
            steps = self.data["jobs"][name]["steps"]
            names = [step.get("name", "") for step in steps]
            gate = names.index("Test the checks against the card about to be published")
            publish = next(i for i, n in enumerate(names) if n.startswith("Publish one "))
            commit = next(i for i, step in enumerate(steps) if step.get("id") == "commit")
            self.assertLess(publish, gate)
            self.assertLess(gate, commit)
            self.assertEqual(steps[gate]["run"].strip(), "python -m unittest discover -s tests")
            self.assertNotIn("if", steps[gate])
            self.assertNotIn("continue-on-error", steps[gate])

    def test_listing_prs_run_the_lock_checks_on_the_published_card(self):
        """The PR's test job publishes its cards into a throwaway copy and runs the refreshes' own checks on it,
        so a stale lock test fails before the merge, not on main."""
        with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
            tests = yaml.safe_load(f)
        steps = tests["jobs"]["test"]["steps"]
        step = next(s for s in steps if str(s.get("name", "")).startswith("Card lock check"))
        self.assertEqual(step.get("if"), "github.event_name == 'pull_request'")
        self.assertNotIn("continue-on-error", step)
        run = step["run"]
        self.assertIn("set -euo pipefail", run)
        self.assertIn("python scripts/publish_one.py --commit HEAD --list", run)
        self.assertIn('cp -a "$GITHUB_WORKSPACE" "$work"; cd "$work"', run)
        self.assertLess(run.index('cd "$work"'), run.index("python scripts/publish_one.py --commit HEAD\n"))
        self.assertNotIn("--dry-run", run)
        self.assertIn("python -m unittest discover -s tests", run)
        self.assertIn("python -m pytest -q $named", run)

if __name__ == "__main__":
    unittest.main()
