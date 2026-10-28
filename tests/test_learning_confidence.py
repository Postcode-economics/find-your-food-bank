"""Confidence sits under auto_apply_rules.json. It can hold a change back. It cannot allow an add or a removal."""
import os, sys, json, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, auto_rules
from test_learning_guards import assert_schedule_and_guards

class Confidence(unittest.TestCase):
    def setUp(self):
        self.rules = auto_rules.load()
        self.before = open(auto_rules.P, encoding="utf-8").read()
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertEqual(open(auto_rules.P, encoding="utf-8").read(), self.before)
    def test_confidence_cannot_add_or_remove(self):
        self.assertFalse(learning.allow_under_rules("new_place", self.rules, 1.0, "foodbanks"))
        self.assertFalse(learning.allow_under_rules("new_place", self.rules, 1.0, "shelters"))
        self.assertFalse(learning.allow_under_rules("new_place", self.rules, 1.0, "warmspaces"))
        self.assertFalse(learning.allow_under_rules("remove_place", self.rules, 1.0))
        self.assertFalse(self.rules["add_new_places"]["foodbanks"])
        self.assertFalse(self.rules["remove_confirmed_closures"])
    def test_confidence_can_only_hold_an_automatic_change(self):
        self.assertTrue(learning.allow_under_rules("opening times", self.rules, None))
        self.assertTrue(learning.allow_under_rules("opening times", self.rules, 0.8))
        self.assertFalse(learning.allow_under_rules("opening times", self.rules, 0.79))
        self.assertFalse(learning.allow_under_rules("not a real kind", self.rules, 1.0))
        self.assertEqual(learning.confidence_for("https://a.org/", {"https://a.org/"}), 0.0)
        self.assertIsNone(learning.confidence_for("https://b.org/", {"https://a.org/"}))
        self.assertFalse(learning.allow_under_rules("clear single new phone on own site", self.rules, 0.0))
    def test_full_check_uses_the_gate(self):
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.allow_under_rules('voucher/walk-in flips'", fc)
        self.assertIn("learning.allow_under_rules('clear single new phone on own site'", fc)
        self.assertIn("learning.allow_under_rules('remove_place'", fc)
        rules = json.load(open(os.path.join(R, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
        self.assertFalse(rules["add_new_places"]["foodbanks"])
        self.assertFalse(rules["remove_confirmed_closures"])

if __name__ == "__main__": unittest.main()
