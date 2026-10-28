"""Dean's past decisions move similar places up and remember his wording. They never answer the next ask."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, auto_rules
from test_learning_guards import assert_schedule_and_guards

class Dean(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertFalse(auto_rules.may_add("foodbanks"))
        self.assertFalse(auto_rules.may_add("shelters"))
        self.assertFalse(auto_rules.may_add("warmspaces"))
    def test_still_asks_and_only_learns_priority_or_wording(self):
        for kind in ("new_place", "remove_place", "phone", "notice"):
            effect = LS.dean_effect(kind)
            self.assertTrue(effect["ask"])
            self.assertFalse(effect["publishes"])
            self.assertEqual(effect["learns"], "priority_or_wording")
    def test_same_host_moves_up_wording_is_not_copied(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = d; LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
        learning.STATE = os.path.join(d, "reports", "learning_state.json")
        try:
            for sub in ("reports", "overrides"): os.makedirs(os.path.join(d, sub))
            items = [dict(id="a", type="foodbank", name="A", website="https://shared.example/a", tel="01000000000"),
                     dict(id="b", type="foodbank", name="B", website="https://shared.example/b", tel="02000000000"),
                     dict(id="c", type="foodbank", name="C", website="https://other.example/", tel="03000000000")]
            data = os.path.join(d, "data.full.js")
            open(data, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            before = open(data).read()
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            json.dump({"a": "07111222333"}, open(os.path.join(d, "overrides", "phones.json"), "w"))
            json.dump({"a": {"notice": "Call before you come", "set": "2026-10-25"}}, open(os.path.join(d, "overrides", "foodbank_notices.json"), "w"))
            approved = {"a": "Dean OK"}
            ap = os.path.join(d, "overrides", "foodbank_approved_new.json")
            json.dump(approved, open(ap, "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            LS.write(o)
            self.assertIn("dean", o["why"]["https://shared.example/b"])
            self.assertNotIn("dean", o["why"].get("https://other.example/", {}))
            self.assertLessEqual(o["boost"]["https://shared.example/b"], learning.BOOST_CAP)
            self.assertEqual(o["dean_wording"]["a"]["text"], "Call before you come")
            self.assertEqual(open(data).read(), before)  # wording was not copied onto B, and B was not added
            self.assertEqual(json.load(open(ap)), approved)
            saved = json.load(open(learning.STATE))
            self.assertEqual(saved["dean_wording"]["a"]["field"], "notice")
            self.assertNotIn("b", saved["dean_wording"])
            self.assertIn("still asked", o["dean_note"])
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__": unittest.main()
