"""A refresh whose every headless render fails must say so in the log.

Run 40875931731 (29 Oct 2026) recorded render_errors 563 of render_attempts 563 and still
finished green. Playwright was not installed until the sense-check step, after build.py
and full_check.py had already rendered. The equality check is separate from the coverage
gate, which stays quiet below its attempt floor.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import intelligent_rails as IR

ROOT = os.path.join(os.path.dirname(__file__), "..")
WF = os.path.join(ROOT, ".github", "workflows")


class EveryRenderFailed(unittest.TestCase):
    def setUp(self):
        IR.reset()

    def tearDown(self):
        IR.reset()

    def test_zero_attempts_is_not_a_failure(self):
        self.assertEqual(IR.every_render_failed("foodbanks"), "")

    def test_one_success_is_not_a_total_failure(self):
        IR.note_render(False, "foodbanks")
        IR.note_render(True, "foodbanks")
        self.assertEqual(IR.every_render_failed("foodbanks"), "")

    def test_equal_counts_name_both_numbers(self):
        for _ in range(563):
            IR.note_render(False, "foodbanks")
        line = IR.every_render_failed("foodbanks")
        self.assertIn("render errors 563 equals render_attempts 563", line)
        self.assertEqual(IR.every_render_failed("shelters"), "")

    def test_build_prints_the_error_and_stops(self):
        with open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8") as fh:
            src = fh.read()
        call = src[src.index("IR.finish_times"):src.index("import schema_version")]
        self.assertIn("IR.every_render_failed('foodbanks')", call)
        self.assertIn("::error::", call)
        self.assertIn("SystemExit(1)", call)

    def test_refresh_installs_chromium_before_the_rebuild(self):
        with open(os.path.join(WF, "refresh.yml"), encoding="utf-8") as fh:
            yml = fh.read()
        install = yml.index("python -m playwright install --with-deps chromium")
        rebuild = yml.index("python scripts/build.py")
        sense = yml.index("python scripts/sense_check.py")
        tests = yml.index("python -m unittest discover -s tests -v")
        self.assertLess(tests, install)
        self.assertLess(install, rebuild)
        self.assertLess(rebuild, sense)
        self.assertEqual(yml.count("python -m playwright install --with-deps chromium"), 1)
        self.assertIn("playwright==1.47.0", yml)
        sense_step = yml[yml.index("- name: Does the result make sense?"):]
        sense_step = sense_step[:sense_step.index("\n      - name:")]
        self.assertNotIn("pip install", sense_step)
        self.assertIn("python scripts/sense_check.py", sense_step)


if __name__ == "__main__":
    unittest.main()
