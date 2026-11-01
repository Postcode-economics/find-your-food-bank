"""A refresh whose every headless render fails must say so, and still finish.

Run 40875931731 (29 Oct 2026) recorded render_errors 563 of render_attempts 563 and still
finished green. Playwright was not installed until the sense-check step, after build.py
and full_check.py had already rendered. The equality check is separate from the coverage
gate, which stays quiet below its attempt floor. It prints a log annotation and writes
the digest alert. It does not exit: the refresh has to publish, and the coverage gate
already holds auto-applies when renders fail.
"""
import json, os, shutil, sys, tempfile, unittest
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

    def test_build_prints_the_error_and_continues(self):
        with open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8") as fh:
            src = fh.read()
        call = src[src.index("IR.finish_times"):src.index("import schema_version")]
        self.assertIn("IR.every_render_failed('foodbanks')", call)
        self.assertIn("::error::", call)
        self.assertIn("IR.alert(failed, ROOT)", call)
        self.assertIn("IR.record_render_failure(ROOT, 'foodbanks', failed)", call)
        self.assertNotIn("SystemExit", call)
        self.assertNotIn("sys.exit", call)

    def test_alert_reaches_the_digest_without_clearing_applies(self):
        # Four failures sit under the coverage gate's attempt floor, so this
        # alert is the only signal the digest would otherwise miss.
        for _ in range(4):
            IR.note_render(False, "foodbanks")
        line = IR.every_render_failed("foodbanks")
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"), exist_ok=True)
            json.dump([{"kind": "fb", "second_run_at": IR._today() + "T12:00:00+00:00", "reverted": False}],
                      open(os.path.join(d, "reports", "times_auto_applied.json"), "w"))
            IR.finish_times(d, "foodbanks", {"x": {"auto_applied": True}, "y": {"status": "held_for_dean", "held": ["fewer days"]}})
            before = IR.load_summary(d)
            self.assertEqual(before["layers"]["foodbanks"]["applied"], 1)
            self.assertEqual(before["layers"]["foodbanks"]["steps"]["times"]["applied_this_run"], 1)
            self.assertEqual(before["layers"]["foodbanks"]["held"], 1)
            self.assertNotIn(line, before.get("alerts") or [])
            self.assertTrue(IR.record_render_failure(d, "foodbanks", line))
            IR.finish(d, "foodbanks", "access", applied=2, held=0)
            data = IR.load_summary(d)
            slot = data["layers"]["foodbanks"]
            self.assertEqual(slot["applied"], 3)
            self.assertEqual(slot["held"], 1)
            self.assertEqual(slot["steps"]["times"]["applied"], 1)
            self.assertIn(line, slot["steps"]["times"]["alerts"])
            self.assertIn(line, data["alerts"])
            self.assertNotIn(line, data.get("would_block") or [])
            text = "\n".join(IR.digest_lines(data))
            self.assertIn(line, text)
            self.assertIn("INTELLIGENT MODE ALERT", text)
            self.assertIn("applied 3 this run, held 1", text)
            os.environ["DRY_RUN"] = "1"
            try:
                self.assertFalse(IR.record_render_failure(d, "foodbanks", line + " again"))
            finally:
                os.environ.pop("DRY_RUN", None)
            self.assertNotIn(line + " again", IR.load_summary(d).get("alerts") or [])
        finally:
            shutil.rmtree(d)

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
