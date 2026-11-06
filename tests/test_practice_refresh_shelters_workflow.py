"""Tests for .github/workflows/practice-refresh-shelters.yml (Speed Item 5: automatic early practice refresh on shelter PRs)
and parity against current main refresh-shelters.yml."""
import os, re, subprocess, sys, unittest

try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRACTICE_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "practice-refresh-shelters.yml")
MAIN_WORKFLOW = os.path.join(ROOT, ".github", "workflows", "refresh-shelters.yml")
BUILD_SHELTERS = os.path.join(ROOT, "scripts", "build_shelters.py")


class TestPracticeRefreshSheltersWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PRACTICE_WORKFLOW, encoding="utf-8") as f:
            cls.practice_content = f.read()
        with open(MAIN_WORKFLOW, encoding="utf-8") as f:
            cls.main_content = f.read()
        cls.practice_data = yaml.safe_load(cls.practice_content)
        cls.main_data = yaml.safe_load(cls.main_content)

    def test_workflow_yaml_valid(self):
        """Workflow must be valid YAML that loads into a dict with jobs."""
        self.assertIsInstance(self.practice_data, dict)
        self.assertIn("jobs", self.practice_data)
        job_key = list(self.practice_data["jobs"].keys())[0]
        self.assertIn("steps", self.practice_data["jobs"][job_key])

    def test_pull_request_trigger_and_branches(self):
        """Must trigger on pull_request to main branch."""
        # Note: PyYAML loads 'on' as True (boolean) unless quoted
        pr_config = self.practice_data.get("on", self.practice_data.get(True, {})).get("pull_request", {})
        self.assertEqual(pr_config.get("branches"), ["main"])

    def test_path_filter_completeness(self):
        """Workflow must include all required paths in its pull_request filter."""
        expected_paths = [
            "overrides/shelters_*",
            "shelters.js",
            "layers.js",
            "scripts/build_shelters.py",
            "scripts/common.py",
            "scripts/place_lock.py",
            "scripts/phone_lock.py",
            "scripts/verify_fresh.py",
            "scripts/publish_gate.py",
            "scripts/refresh_guard.py",
            "scripts/sense_check.py",
            "tests/test_final_lock.py",
            "tests/test_verify_fresh_hand_wins.py",
            ".github/workflows/refresh-shelters.yml",
            ".github/workflows/practice-refresh-shelters.yml",
        ]
        pr_config = self.practice_data.get("on", self.practice_data.get(True, {})).get("pull_request", {})
        actual_paths = pr_config.get("paths", [])
        for p in expected_paths:
            self.assertIn(p, actual_paths, f"Missing required path filter: {p}")

    def test_same_repo_prs_only(self):
        """Workflow job must run only for same-repo PRs."""
        job = list(self.practice_data["jobs"].values())[0]
        job_condition = job.get("if", "")
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", job_condition)

    def test_permissions_read_only(self):
        """Workflow permissions must be contents: read only."""
        permissions = self.practice_data.get("permissions", {})
        self.assertEqual(permissions, {"contents": "read"})

    def test_concurrency_group_and_cancel_in_progress(self):
        """Concurrency group per PR with cancel-in-progress: true."""
        concurrency = self.practice_data.get("concurrency", {})
        self.assertTrue(concurrency.get("cancel-in-progress"))
        group = concurrency.get("group", "")
        self.assertIn("practice-refresh-shelters-pr-", group)
        self.assertIn("github.event.pull_request.number", group)

    def test_checkout_persist_credentials_false(self):
        """Checkout step must set persist-credentials: false."""
        job = list(self.practice_data["jobs"].values())[0]
        checkout_steps = [s for s in job["steps"] if "actions/checkout" in str(s.get("uses", ""))]
        self.assertTrue(checkout_steps, "Missing checkout step")
        with_clause = checkout_steps[0].get("with", {})
        self.assertFalse(with_clause.get("persist-credentials", True))

    def test_no_secrets_or_tokens(self):
        """No secrets (PRIVATE_BLOCKLIST, BREVO_API_KEY, etc.) or tokens in the practice workflow."""
        self.assertNotIn("secrets.PRIVATE_BLOCKLIST", self.practice_content)
        self.assertNotIn("secrets.BREVO_API_KEY", self.practice_content)
        self.assertNotIn("secrets.", self.practice_content)
        self.assertNotIn("github.token", self.practice_content)
        self.assertNotIn("GH_TOKEN", self.practice_content)

    def test_no_side_effects_steps(self):
        """No commit, IndexNow, email or issue steps."""
        self.assertNotIn("indexnow.py", self.practice_content)
        self.assertNotIn("git commit", self.practice_content)
        self.assertNotIn("findings_report.py", self.practice_content)
        self.assertNotIn("new_live_email.py", self.practice_content)
        self.assertNotIn("alert.py", self.practice_content)

    def test_practice_run_guard_step(self):
        """Must have Practice-run guard step that fails if staged changes or HEAD changed from baseline."""
        self.assertIn("name: Practice-run guard", self.practice_content)
        self.assertIn("if: always()", self.practice_content)
        self.assertIn("git diff --cached --quiet", self.practice_content)
        self.assertIn("LIVE_BASELINE", self.practice_content)

    def test_parity_gates_against_main_refresh_shelters(self):
        """Gate steps must match the gates in refresh-shelters.yml (excluding blocklist-secret steps):
        build_shelters.py, verify_fresh.py shelters, publish_gate.py shelters, shelter_contacts.py check,
        publish_gate.py check, refresh_guard.py shelters, sense_check.py, swep.py, validate.py gate."""
        expected_commands = [
            "python scripts/build_shelters.py",
            "python scripts/verify_fresh.py shelters",
            "python scripts/publish_gate.py shelters",
            "python scripts/shelter_contacts.py check",
            "python scripts/publish_gate.py check",
            "python scripts/refresh_guard.py shelters",
            "python scripts/sense_check.py",
            "python scripts/swep.py",
            "python scripts/validate.py gate",
        ]
        job = list(self.practice_data["jobs"].values())[0]
        practice_runs = [s.get("run", "") for s in job["steps"]]

        for cmd in expected_commands:
            self.assertTrue(any(cmd in r for r in practice_runs), f"Expected command missing from practice workflow: {cmd}")
            # Parity check: verify it is also present in main refresh-shelters.yml
            self.assertIn(cmd, self.main_content, f"Command {cmd} should also be in main refresh-shelters.yml")

        # Verify ordering of gates matches the order in refresh-shelters.yml
        pos = 0
        for cmd in expected_commands:
            idx = self.practice_content.index(cmd)
            self.assertGreaterEqual(idx, pos, f"Command {cmd} is out of order")
            pos = idx

    def test_final_lock_runs_before_output_is_written_in_build_shelters(self):
        """Verify build_shelters.py calls final_lock before write_js."""
        with open(BUILD_SHELTERS, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("place_lock.final_lock(", src)
        self.assertIn('write_js(OUT, "SHELTERS"', src)
        lock_idx = src.index("place_lock.final_lock(")
        write_idx = src.index('write_js(OUT, "SHELTERS"')
        self.assertLess(lock_idx, write_idx, "place_lock.final_lock must run before write_js in build_shelters.py")


if __name__ == "__main__":
    unittest.main()
