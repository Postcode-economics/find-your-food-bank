"""Per-place update rhythm: only observed gaps between real changes. No invented interval."""
import os, sys, json, datetime, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class Rhythm(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_two_gaps_then_due(self):
        s = learning.load(os.devnull)
        learning.record(s, "https://a.org/", "2026-01-01", True, changed=True)
        learning.record(s, "https://a.org/", "2026-02-01", True, changed=True)  # one gap: not enough
        self.assertEqual(learning.rhythm_factor(s["keys"]["https://a.org/"], "2026-03-15"), 0.0)
        learning.record(s, "https://a.org/", "2026-03-01", True, changed=True)
        self.assertEqual(learning.rhythm_factor(s["keys"]["https://a.org/"], "2026-03-01"), 0.0)  # just changed
        self.assertGreater(learning.rhythm_factor(s["keys"]["https://a.org/"], "2026-04-05"), 0.9)
        learning.record(s, "https://quiet.org/", "2026-01-01", True)
        self.assertEqual(learning.rhythm_factor(s["keys"]["https://quiet.org/"], "2026-04-05"), 0.0)
    def test_weekly_floor_still_beats_a_quiet_rhythm(self):
        s = learning.load(os.devnull)
        learning.record(s, "quiet", "2026-10-01", True)
        order, _, _ = learning.plan(s, ["quiet"], "2026-10-08", budget=0)
        self.assertEqual(order, ["quiet"])  # 7 days, checked even with no rhythm and a zero budget
    def test_signal_sits_under_the_cap(self):
        import tempfile, shutil
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = d; LS.OUT = os.path.join(d, "x"); LS.MD = os.path.join(d, "y")
        learning.STATE = os.path.join(d, "reports", "learning_state.json"); os.makedirs(os.path.join(d, "reports"))
        try:
            items = [dict(id="a", type="foodbank", website="https://a.org/", tel="01234567890")]
            open(os.path.join(d, "data.full.js"), "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            s = learning.load(learning.STATE)
            for day in ("2026-01-01", "2026-02-01", "2026-03-01"):
                learning.record(s, "https://a.org/", day, True, changed=True)
            learning.save(s, learning.STATE)
            o = LS.build(datetime.date(2026, 4, 5))
            self.assertIn("rhythm", o["why"]["https://a.org/"])
            self.assertLessEqual(o["boost"]["https://a.org/"], learning.BOOST_CAP)
            self.assertIn("https://a.org/", o["boosted_by"]["rhythm"])
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__": unittest.main()
