"""The morning note compares installed libraries with the pins. It never upgrades them."""
import os, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import pins
from test_learning_guards import assert_schedule_and_guards

class Pins(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        req = open(os.path.join(R, "requirements.txt"), encoding="utf-8").read()
        self.assertIn("playwright==1.47.0", req)
        src = open(os.path.join(R, "scripts", "pins.py"), encoding="utf-8").read()
        self.assertNotIn("pip", src)
        self.assertNotIn("subprocess", src)
    def test_report_names_a_mismatch_and_an_unpinned_import(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "sample.py"), "w").write("import playwright\nimport madeuplib\nimport json\n")
        lines = pins.report("playwright==1.47.0\n", d, lambda name: "9.9.9")
        text = " ".join(lines)
        self.assertIn("pinned to 1.47.0 but this machine has 9.9.9", text)
        self.assertIn("madeuplib", text)
        self.assertNotIn("json", text)
    def test_a_match_is_quiet_and_a_missing_install_is_named(self):
        lines = pins.report("playwright==1.47.0\n", tempfile.mkdtemp(), lambda name: "1.47.0")
        self.assertIn("matches its pin 1.47.0", " ".join(lines))
        missing = pins.report("playwright==1.47.0\n", tempfile.mkdtemp(), lambda name: None)
        self.assertIn("not installed here", " ".join(missing))
    def test_repo_requirements_are_what_the_note_reads(self):
        text = open(os.path.join(R, "requirements.txt"), encoding="utf-8").read()
        self.assertEqual(pins.parse_pins(text), {"playwright": "1.47.0"})

if __name__ == "__main__":
    unittest.main()
