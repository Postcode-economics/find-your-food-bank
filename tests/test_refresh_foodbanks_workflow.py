"""Tests for the practice-run guard and non-main ref protections in .github/workflows/refresh.yml."""
import os, subprocess, sys, unittest

try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "refresh.yml")


class RefreshFoodbanksPracticeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.content = f.read()

    def test_workflow_yaml_valid(self):
        """Workflow must be valid YAML that loads into a dict with jobs."""
        data = yaml.safe_load(self.content)
        self.assertIsInstance(data, dict)
        self.assertIn("jobs", data)
        self.assertIn("refresh", data["jobs"])
        self.assertIn("steps", data["jobs"]["refresh"])

    def test_concurrency_group(self):
        """Concurrency group: 'refresh' on main, 'refresh-pr-<branch>' on any other ref."""
        pattern = r"group:\s*\${{\s*github\.ref\s*==\s*'refs/heads/main'\s*&&\s*'refresh'\s*\|\|\s*format\('refresh-pr-\{0\}',\s*github\.ref_name\)\s*}}"
        self.assertRegex(self.content, pattern)

    def test_every_gh_token_is_ref_conditional(self):
        """GH_TOKEN must be empty on non-main refs for every step that has it."""
        gh_token_lines = [line.strip() for line in self.content.splitlines() if "GH_TOKEN:" in line]
        self.assertGreaterEqual(len(gh_token_lines), 8)
        expected = "GH_TOKEN: ${{ github.ref == 'refs/heads/main' && github.token || '' }}"
        for line in gh_token_lines:
            self.assertEqual(line, expected)

    def test_practice_skip_echoes_present(self):
        """On non-main refs, skipped steps echo fixed lines:
        'PRACTICE: IndexNow skipped', 'PRACTICE: Brevo skipped' or 'PRACTICE: issues skipped'."""
        self.assertIn("PRACTICE: IndexNow skipped", self.content)
        self.assertIn("PRACTICE: Brevo skipped", self.content)
        self.assertIn("PRACTICE: issues skipped", self.content)

    def test_publishing_steps_run_only_on_main(self):
        """Publishing steps (Commit if changed, IndexNow, findings email, new place email, digest, alerts)
        must only perform live actions on main with github.ref == 'refs/heads/main'."""
        self.assertIn("if: github.ref == 'refs/heads/main'", self.content)

    def test_brevo_and_commit_gate_intact(self):
        """Keep the line BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }} exactly as it is,
        and keep steps.commit.outcome == 'success' email gate."""
        self.assertIn("BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}", self.content)
        self.assertIn("steps.commit.outcome == 'success'", self.content)

    def test_private_blocklist_intact(self):
        """Keep PRIVATE_BLOCKLIST reaching the gates."""
        self.assertIn("PRIVATE_BLOCKLIST: ${{ secrets.PRIVATE_BLOCKLIST }}", self.content)

    def test_final_practice_guard_step(self):
        """A final step runs only on non-main refs, fails if anything is STAGED or HEAD differs from baseline,
        and does NOT use a dirty-tree check."""
        self.assertIn("name: Practice-run guard", self.content)
        self.assertIn("if: always() && github.ref != 'refs/heads/main'", self.content)
        self.assertIn("git diff --cached --quiet", self.content)
        self.assertIn("LIVE_BASELINE", self.content)
        # Ensure no dirty working-tree check like 'git diff --quiet' or 'git status --porcelain'
        self.assertNotIn("git diff --quiet\n", self.content)
        self.assertNotIn("git status --porcelain", self.content)


if __name__ == "__main__":
    unittest.main()
