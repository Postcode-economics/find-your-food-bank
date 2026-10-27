"""Report a problem submissions raise a place's priority. They never edit the listing. No file, no effect."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

def stand(d):
    os.makedirs(os.path.join(d, "reports"), exist_ok=True)
    items = [dict(id="a", type="foodbank", website="https://a.org/", tel="01000000000", name="A"),
             dict(id="b", type="foodbank", website="https://b.org/", tel="02000000000", name="B")]
    path = os.path.join(d, "data.full.js")
    open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
    json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
    return path

class Problems(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_missing_file_has_no_effect(self):
        stand(self.d)
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["problem_note"])
        self.assertNotIn("problem", str(o["why"]))
    def test_a_submission_raises_that_place_only(self):
        data = stand(self.d); before = open(data).read()
        os.makedirs(os.path.join(self.d, "overrides"))
        json.dump({"_about": "from the Report a problem form", "b": [{"when": "2026-10-25", "what": "times"}]},
                  open(os.path.join(self.d, "overrides", "problem_reports.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("problem", o["why"]["https://b.org/"])
        self.assertNotIn("problem", o["why"].get("https://a.org/", {}))
        self.assertLessEqual(o["boost"]["https://b.org/"], learning.BOOST_CAP)
        self.assertGreater(o["why"]["https://b.org/"]["problem"], 0)
        self.assertEqual(open(data).read(), before)

if __name__ == "__main__": unittest.main()
