"""The monthly brake drill uses a copy. It does not write the live brake file or the real counts."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, brake_drill
from test_learning_guards import assert_schedule_and_guards

class Drill(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        os.makedirs(os.path.join(self.d, "reports"))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertIn("5 3,11,19 * * *", open(os.path.join(R, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read())
    def test_a_short_history_invents_nothing(self):
        hist = [{"day": "2026-10-01", "changes": 2}]
        info = brake_drill.drill(hist, note_path=os.path.join(self.d, "drill.md"))
        self.assertFalse(info["stop"]); self.assertIsNone(info["spike"]); self.assertFalse(info["published"])
        self.assertEqual(hist, [{"day": "2026-10-01", "changes": 2}])
        self.assertIn("not enough", info["line"])
        self.assertIn("Nothing was published", open(os.path.join(self.d, "drill.md"), encoding="utf-8").read())
    def test_the_spike_stops_a_copy_and_leaves_the_real_counts(self):
        hist = [{"day": "2026-10-0%d" % i, "changes": 2} for i in range(1, 5)]
        live = os.path.join(self.d, "reports", "anomaly_brake.md")
        open(live, "w").write("LIVE\n")
        info = brake_drill.drill(list(hist))
        self.assertTrue(info["stop"]); self.assertFalse(info["published"]); self.assertGreaterEqual(info["spike"], 10)
        self.assertEqual(hist, [{"day": "2026-10-0%d" % i, "changes": 2} for i in range(1, 5)])
        self.assertEqual(open(live).read(), "LIVE\n")
        self.assertRaises(ValueError, brake_drill.drill, hist, live)
        self.assertEqual(open(live).read(), "LIVE\n")
    def test_only_the_first_of_the_month_writes_a_drill(self):
        counts = [{"day": "2026-10-0%d" % i, "changes": 2} for i in range(1, 5)]
        json.dump({"version": 1, "keys": {}, "change_counts": counts}, open(learning.STATE, "w"))
        open(os.path.join(self.d, "data.full.js"), "w").write('window.FB_DATA={"items":[]};')
        json.dump({"sites": {}}, open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        live = os.path.join(self.d, "reports", "anomaly_brake.md")
        open(live, "w").write("LIVE\n")
        quiet = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no drill", quiet["drill_note"])
        self.assertFalse(os.path.exists(os.path.join(self.d, "reports", "anomaly_brake_drill.md")))
        o = LS.build(datetime.date(2026, 11, 1))
        self.assertIn("would be stopped", o["drill_note"])
        self.assertIn("Nothing was published", open(os.path.join(self.d, "reports", "anomaly_brake_drill.md"), encoding="utf-8").read())
        self.assertEqual(open(live).read(), "LIVE\n")
        saved = json.load(open(learning.STATE))
        self.assertEqual(saved["change_counts"], counts)
        self.assertNotIn("anomaly", saved)

if __name__ == "__main__":
    unittest.main()
