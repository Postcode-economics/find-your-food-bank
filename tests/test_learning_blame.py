"""Hand corrections are blamed on the source that supplied the place. Nothing is rewritten."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class Blame(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_blame_is_by_source_and_field(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
        LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
        try:
            for sub in ("reports", "overrides"): os.makedirs(os.path.join(d, sub))
            items = [dict(id="a", type="foodbank", givefood="g", website="https://a.org/", tel="01000000000"),
                     dict(id="ifan-c", type="foodbank", website="https://c.org/", tel="02000000000")]
            path = os.path.join(d, "data.full.js")
            open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            before = open(path).read()
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            json.dump({"ifan-c": "02000000000"}, open(os.path.join(d, "overrides", "phones.json"), "w"))
            json.dump({"a": {"notice": "Ring first"}}, open(os.path.join(d, "overrides", "foodbank_notices.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26)); LS.write(o)
            self.assertEqual(o["source_blame"].get("IFAN"), {"phone": 1})
            self.assertEqual(o["source_blame"].get("Give Food"), {"notice": 1})
            self.assertNotIn("chosen", json.dumps(o["source_blame"]))
            self.assertEqual(open(path).read(), before)
            self.assertEqual(json.load(open(learning.STATE))["source_blame"]["IFAN"]["phone"], 1)
            self.assertIn("IFAN (phone 1)", open(LS.MD).read())
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__": unittest.main()
