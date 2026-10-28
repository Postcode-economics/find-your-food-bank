"""A broken or suddenly smaller hand file stops the publish. A confirmed shrink is allowed."""
import os, sys, json, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import override_check
from test_learning_guards import assert_schedule_and_guards

class Overrides(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertIn("override_check.assess", open(os.path.join(R, "scripts", "publish_gate.py"), encoding="utf-8").read())
    def test_shrink_is_held_until_confirmed(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "overrides"))
        phones = os.path.join(d, "overrides", "phones.json")
        json.dump({"a": "1", "b": "2", "c": "3", "d": "4"}, open(phones, "w"))
        ok, why = override_check.assess(d)
        self.assertTrue(ok)
        json.dump({"a": "1"}, open(phones, "w"))
        ok, why = override_check.assess(d)
        self.assertFalse(ok)
        self.assertIn("held for Dean", why)
        self.assertIn("Nothing was published", open(os.path.join(d, "reports", "override_check.md"), encoding="utf-8").read())
        json.dump({"overrides/phones.json": 1}, open(os.path.join(d, "overrides", "shrink_ok.json"), "w"))
        ok, why = override_check.assess(d)
        self.assertTrue(ok)
        self.assertIn("confirmed", why)
    def test_broken_json_is_held_and_a_missing_file_is_skipped(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "overrides"))
        open(os.path.join(d, "overrides", "phones.json"), "w").write("{")
        ok, why = override_check.assess(d)
        self.assertFalse(ok)
        self.assertIn("not valid JSON", why)
        empty = tempfile.mkdtemp()
        ok, why = override_check.assess(empty)
        self.assertTrue(ok)

if __name__ == "__main__":
    unittest.main()
