"""Sunday accuracy grade turns a weak signal down one step, and leaves the rest alone."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

def world(d, day_finds):
    os.makedirs(os.path.join(d, "reports"))
    open(os.path.join(d, "data.full.js"), "w").write('window.FB_DATA={"items":[]};')
    json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
    keys = {}
    def ent(find):
        return {"checks": 4, "finds": 1 if find else 0, "last_find": "2026-10-24" if find else None, "last_check": "2026-10-24"}
    for i in range(5):
        keys["w%d" % i] = ent(False); keys["s%d" % i] = ent(True); keys["r%d" % i] = ent(True)
    keys["only"] = ent(False)
    s = {"version": 1, "keys": keys, "total_checks": 40, "history": []}
    json.dump(s, open(os.path.join(d, "reports", "learning_state.json"), "w"))
    prev = {"weights": dict(LS.DEFAULT_W), "boosted_by": {
        "signal": ["w%d" % i for i in range(5)],
        "season": ["s%d" % i for i in range(5)],
        "visitor": ["only"]}}
    json.dump(prev, open(os.path.join(d, "reports", "learning_signals.json"), "w"))

class Accuracy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "out.json"); LS.MD = os.path.join(self.d, "reports", "review.md")
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertEqual(learning.FLOOR_DAYS, 7)
    def test_sunday_turns_only_the_weak_signal_down_one_step(self):
        world(self.d, None)
        o = LS.build(datetime.date(2026, 10, 25))  # Sunday
        self.assertEqual(o["accuracy"]["signal"]["note"], "turned down")
        self.assertAlmostEqual(o["weights"]["signal"], LS.DEFAULT_W["signal"] * 0.9, places=4)
        self.assertGreater(o["weights"]["signal"], LS.DEFAULT_W["signal"] * 0.9 * 0.9)  # one step, not two
        self.assertEqual(o["accuracy"]["visitor"]["note"], "not enough data")
        self.assertAlmostEqual(o["weights"]["visitor"], LS.DEFAULT_W["visitor"])
        self.assertEqual(o["accuracy"]["season"]["note"], "kept")
        self.assertGreaterEqual(o["weights"]["season"], LS.DEFAULT_W["season"])
        for k, base in LS.DEFAULT_W.items():
            self.assertGreaterEqual(o["weights"][k], base * LS.LO - 1e-9)
            self.assertLessEqual(o["weights"][k], base * LS.HI + 1e-9)
    def test_other_days_do_not_change_weights(self):
        world(self.d, None)
        o = LS.build(datetime.date(2026, 10, 26))  # Monday
        self.assertEqual(o["accuracy"], {})
        self.assertAlmostEqual(o["weights"]["signal"], LS.DEFAULT_W["signal"])

if __name__ == "__main__": unittest.main()
