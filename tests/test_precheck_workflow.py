"""Unit tests for Item 3 precheck job and fail-on-skip/cancelled assertions in .github/workflows/tests.yml."""
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
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "tests.yml")
FAST_TESTS = os.path.join(ROOT, "tests", "fast_tests.txt")


class PrecheckWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as f:
            cls.content = f.read()
        cls.data = yaml.safe_load(cls.content)

    def test_workflow_valid_yaml(self):
        self.assertIsInstance(self.data, dict)
        self.assertIn("jobs", self.data)

    def test_fast_tests_file_exists_and_non_empty(self):
        self.assertTrue(os.path.isfile(FAST_TESTS))
        with open(FAST_TESTS, encoding="utf-8") as f:
            lines = [line.strip() for line in f.read().splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 1)
        for line in lines:
            self.assertTrue(os.path.exists(os.path.join(ROOT, line)), f"{line} does not exist")

    def test_precheck_job_configured(self):
        jobs = self.data["jobs"]
        self.assertIn("precheck", jobs)
        precheck = jobs["precheck"]
        self.assertEqual(precheck["needs"], "changes")
        # runs when quick != '1'
        self.assertIn("needs.changes.outputs.quick != '1'", str(precheck.get("if", "")))

    def test_precheck_runs_pycompile_quickcheck_and_pytest(self):
        self.assertIn("python -m py_compile", self.content)
        self.assertIn("python scripts/quick_check.py", self.content)
        self.assertIn("python -m pytest -q -x", self.content)
        self.assertIn("tests/fast_tests.txt", self.content)
        self.assertIn("RUNNER_TEMP", self.content)

    def test_heavy_jobs_depend_on_precheck(self):
        jobs = self.data["jobs"]
        heavy = ["test", "journeys", "browser-tests", "design-lock", "old-links"]
        for job_name in heavy:
            self.assertIn(job_name, jobs, f"Job {job_name} missing")
            needs = jobs[job_name].get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            self.assertIn("precheck", needs, f"Job {job_name} does not depend on precheck: {needs}")

    def test_browser_tests_all_checks_precheck_and_shards(self):
        b_all = self.data["jobs"]["browser-tests-all"]
        needs = b_all.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        self.assertIn("precheck", needs)
        self.assertIn("browser-tests", needs)

    def test_tests_passed_guard_fails_on_skipped_or_cancelled(self):
        tp = self.data["jobs"]["tests-passed"]
        needs = tp.get("needs", [])
        self.assertIn("precheck", needs)
        self.assertIn("test", needs)
        # Check that steps verify precheck, test, and needed jobs
        self.assertIn(".precheck.result", self.content)
        self.assertIn("browser_needed", self.content)
        self.assertIn("oldlinks_needed", self.content)
        self.assertIn("design_needed", self.content)
        self.assertIn("journeys_needed", self.content)

    def test_push_schedule_dispatch_run_all(self):
        # changes job run_all logic for push, nightly schedule, dispatch
        self.assertIn("Only pull_request runs narrow", self.content)
        self.assertIn("schedule", self.content)
        self.assertIn("workflow_dispatch", self.content)


if __name__ == "__main__":
    unittest.main()
