"""When sources disagree, flag Dean. Never pick a value."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class Conflicts(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json"); LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        os.makedirs(os.path.join(self.d, "reports"))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_disagreement_is_flagged_and_not_picked(self):
        items = [dict(id="a", type="foodbank", name="A", website="https://a.org/", tel="01111111111", phone="01111111111"),
                 dict(id="b", type="foodbank", name="B", website="https://b.org/", tel="02222222222", phone="02222222222")]
        path = os.path.join(self.d, "data.full.js")
        open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
        before = open(path).read()
        json.dump({"sites": {"https://a.org/": {"phones": ["01111111111"], "fail_runs": 0},
                             "https://b.org/": {"phones": ["09999999999"], "fail_runs": 0}}},
                  open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26)); LS.write(o)
        self.assertEqual([c["id"] for c in o["conflicts"]], ["b"])
        self.assertIsNone(o["conflicts"][0]["chosen"])
        self.assertEqual(o["conflicts"][0]["action"], "flag_for_dean")
        self.assertIn("conflict", o["why"]["https://b.org/"])
        self.assertNotIn("conflict", o["why"].get("https://a.org/", {}))
        self.assertLessEqual(o["boost"]["https://b.org/"], learning.BOOST_CAP)
        self.assertEqual(open(path).read(), before)
        self.assertIn("Nothing was picked", open(LS.MD).read())
        saved = json.load(open(path)) if False else json.loads(open(path).read().split("=", 1)[1].rstrip(";"))
        self.assertEqual(saved["items"][1]["tel"], "02222222222")

if __name__ == "__main__": unittest.main()
