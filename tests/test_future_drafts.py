"""Problem-report drafts wait for Dean. They never apply, and they never change a listing."""
import os, sys, json, datetime, tempfile, shutil, inspect, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, problem_drafts
from test_learning_guards import assert_schedule_and_guards

class Drafts(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        for sub in ("reports", "overrides"): os.makedirs(os.path.join(self.d, sub))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        src = inspect.getsource(LS.problem_reports)
        self.assertIn("problem_reports.json", src)
        self.assertNotIn("problem_report_drafts", src)
    def test_a_draft_cannot_apply_or_name_a_place(self):
        path = os.path.join(self.d, "overrides", "problem_report_drafts.json")
        saved = problem_drafts.save(path, [{
            "when": "2026-10-26", "text": "The hours for Place A look wrong",
            "place_id": "a", "apply": True,
        }])
        self.assertFalse(saved["apply"])
        self.assertIsNone(saved["drafts"][0]["place_id"])
        self.assertFalse(saved["drafts"][0]["apply"])
        again = problem_drafts.load(path)
        self.assertEqual(again[0]["place_id"], None)
        self.assertFalse(again[0]["apply"])
        self.assertFalse(any(r.get("apply") for r in again))
    def test_a_draft_does_not_change_priority_or_the_listing(self):
        items = [dict(id="a", type="foodbank", website="https://a.org/", tel="01000000000", name="A", postcode="LS1 1AA")]
        data = os.path.join(self.d, "data.full.js")
        open(data, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
        before = open(data).read()
        json.dump({"sites": {}}, open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        problem_drafts.save(os.path.join(self.d, "overrides", "problem_report_drafts.json"),
                            [{"text": "please close this food bank", "place_id": "a", "apply": True}])
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["problem_note"])
        self.assertIn("not applied", o["draft_note"])
        self.assertNotIn("problem", str(o["why"]))
        self.assertEqual(open(data).read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.d, "overrides", "problem_reports.json")))
        self.assertIn("do not change a listing", "\n".join(LS.digest_lines(o)))

if __name__ == "__main__":
    unittest.main()
