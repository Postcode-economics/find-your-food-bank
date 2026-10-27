"""Real changes are counted per week, without names or phone numbers. The season boost stays as it is."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import entry_history as E, learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

def w(p, items): open(p, "w").write("var D=" + json.dumps({"items": items}) + ";")

class Tally(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_phone_is_counted_and_not_stored(self):
        d = tempfile.mkdtemp(); P = lambda n: os.path.join(d, n)
        w(P("d.js"), [{"id": "b", "name": "B", "phone": "01000000000", "address": "1 Road"}])
        E.update(P("d.js"), P("s.json"), P("h.json"), P("c.json"), when="2026-10-20T00:00:00+00:00")
        w(P("d.js"), [{"id": "b", "name": "B", "phone": "01000000001", "address": "2 Road"}])
        E.update(P("d.js"), P("s.json"), P("h.json"), P("c.json"), when="2026-10-26T00:00:00+00:00")
        raw = open(P("week_counts.json"), encoding="utf-8").read()
        self.assertNotIn("01000000001", raw)
        self.assertNotIn("2 Road", raw)
        self.assertNotIn("B", raw)
        counts = json.loads(raw)["counts"]
        self.assertEqual(counts, {"2026-W44": 1})
        hist = json.load(open(P("h.json")))["b"]
        self.assertIn("01000000001", [c.get("new") for c in hist])
    def test_two_years_do_not_change_the_season_boost(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            os.makedirs(os.path.join(d, "logs")); os.makedirs(os.path.join(d, "reports"))
            json.dump({"counts": {"2025-W01": 3, "2026-W01": 4}}, open(os.path.join(d, "logs", "week_counts.json"), "w"))
            json.dump({}, open(os.path.join(d, "logs", "entry_history.json"), "w"))
            open(os.path.join(d, "data.full.js"), "w").write("window.FB_DATA=" + json.dumps({"items": []}) + ";")
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertEqual(o["season"]["boost"], 0.0)
            self.assertIn("season boost is unchanged", o["tally_note"])
            self.assertIn("2 year", o["tally_note"])
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__":
    unittest.main()
