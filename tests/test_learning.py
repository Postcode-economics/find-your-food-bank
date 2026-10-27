"""Self-learning sweeps (Dean, 25 Oct 2026, 08:01): scoring, ordering, weekly floor, back-off, method memory,
persistence across runs, digest section; and that the sweeps only change ORDER, never the published-data rules."""
import os, sys, json, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import learning as LR

class Scoring(unittest.TestCase):
    def test_reward_and_priority(self):
        s = LR.load(os.devnull)
        for d in ("2026-10-20", "2026-10-21", "2026-10-22"): LR.record(s, "good", d, True, finds=1); LR.record(s, "dull", d, True, finds=0)
        self.assertGreater(LR.reward(s["keys"]["good"]), LR.reward(s["keys"]["dull"]))
        t = "2026-10-23"
        self.assertGreater(LR.priority(s, "good", t), LR.priority(s, "dull", t))
        self.assertGreater(LR.priority(s, "dull", t, gap=1.0), LR.priority(s, "dull", t, gap=0.0))  # missing phone/times = dig more
        self.assertGreater(LR.priority(s, "new", t), 0)  # unseen keys get an exploration bonus
        self.assertEqual(LR.priority(s, "dull", t, boost=10), LR.priority(s, "dull", t, boost=LR.BOOST_CAP))  # one shared cap
    def test_old_results_fade(self):
        s = LR.load(os.devnull)
        LR.record(s, "old", "2026-01-01", True, finds=1)
        at_the_time = LR.reward(s["keys"]["old"], "2026-01-01")
        later = LR.reward(s["keys"]["old"], "2026-07-01")  # same result, read half a year on
        self.assertGreater(at_the_time, later)
        LR.record(s, "old", "2026-07-01", True, finds=0)
        LR.record(s, "fresh", "2026-07-01", True, finds=1)
        self.assertGreater(LR.reward(s["keys"]["fresh"], "2026-07-01"), LR.reward(s["keys"]["old"], "2026-07-01"))
    def test_not_reached_records_nothing(self):
        s = LR.load(os.devnull); LR.record(s, "x", "2026-10-25", None); self.assertNotIn("x", s["keys"])

class Ordering(unittest.TestCase):
    def setUp(self):
        self.s = LR.load(os.devnull)
        for d in ("2026-10-22", "2026-10-23", "2026-10-24"):
            LR.record(self.s, "rich", d, True, finds=1); LR.record(self.s, "stable", d, True, finds=0)
        LR.record(self.s, "old", "2026-10-15", True, finds=0)  # 10 days ago: weekly floor
    def test_floor_first_then_priority(self):
        order, skipped, p = LR.plan(self.s, ["stable", "rich", "old", "brandnew"], "2026-10-25")
        self.assertEqual(set(order[:2]), {"old", "brandnew"})  # never checked / >= 7 days: always this run
        self.assertLess(order.index("rich"), order.index("stable"))
    def test_budget_keeps_floor(self):
        order, _, _ = LR.plan(self.s, ["stable", "rich", "old"], "2026-10-25", budget=2)
        self.assertEqual(order, ["old", "rich"])
        order, _, _ = LR.plan(self.s, ["stable", "rich", "old"], "2026-10-25", budget=0)
        self.assertEqual(order, ["old"])  # floor beats the budget
    def test_stable_still_checked_weekly(self):
        s = LR.load(os.devnull); LR.record(s, "stable", "2026-10-01", True)
        for d in range(2, 9): LR.record(s, "rich", "2026-10-0%d" % d, True, finds=1)
        order, _, _ = LR.plan(s, ["stable", "rich"], "2026-10-08", budget=1)
        self.assertIn("stable", order)

class Backoff(unittest.TestCase):
    def test_backoff_then_retry_within_floor(self):
        s = LR.load(os.devnull)
        LR.record(s, "bad", "2026-10-20", False); LR.record(s, "bad", "2026-10-21", False); LR.record(s, "bad", "2026-10-22", False)  # 3 fails: rest 4 days
        self.assertIn("bad", LR.plan(s, ["bad"], "2026-10-24")[1])
        self.assertIn("bad", LR.plan(s, ["bad"], "2026-10-26")[0])
        for i in range(10): LR.record(s, "bad", "2026-10-26", False)
        self.assertIn("bad", LR.plan(s, ["bad"], "2026-10-30")[1])
        self.assertIn("bad", LR.plan(s, ["bad"], "2026-11-02")[0])  # never past the weekly floor
        LR.record(s, "bad", "2026-11-02", True); self.assertEqual(s["keys"]["bad"]["consec_fail"], 0)
    def test_single_failure_no_backoff(self):
        s = LR.load(os.devnull); LR.record(s, "x", "2026-10-24", False)
        self.assertIn("x", LR.plan(s, ["x"], "2026-10-25")[0])

class Methods(unittest.TestCase):
    def test_last_working_method_first(self):
        s = LR.load(os.devnull)
        LR.record(s, "site", "2026-10-24", True, method="facebook"); LR.record(s, "site", "2026-10-25", False, method="own_site")
        self.assertEqual(LR.method_order(s, "site", ["own_site", "facebook", "givefood"])[0], "facebook")
        self.assertEqual(LR.method_order(s, "unknown", ["own_site", "facebook"]), ["own_site", "facebook"])

class Persistence(unittest.TestCase):
    def test_round_trip_and_digest(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "learning_state.json"); s = LR.load(p)
            LR.record(s, "a", "2026-10-24", True, finds=1); LR.snapshot(s, "2026-10-24"); LR.save(s, p)
            s2 = LR.load(p); LR.record(s2, "a", "2026-10-25", True, finds=1); LR.record(s2, "b", "2026-10-25", False); LR.record(s2, "b", "2026-10-25", False)
            LR.snapshot(s2, "2026-10-25"); LR.save(s2, p)
            s3 = LR.load(p); self.assertEqual(s3["keys"]["a"]["checks"], 2); self.assertEqual(s3["total_checks"], 4); self.assertEqual(len(s3["history"]), 2)
            txt = "\n".join(LR.digest_lines(s3, "2026-10-25"))
            self.assertIn("## What the system learned", txt)
            self.assertIn("a (score up by", txt); self.assertIn("b (failed 2 times in a row)", txt)

class Wiring(unittest.TestCase):
    def test_sweeps_use_learning_only_for_order(self):
        fc = open(os.path.join(ROOT, "scripts", "full_check.py")).read(); sw = open(os.path.join(ROOT, "scripts", "sweep_daily.py")).read()
        dg = open(os.path.join(ROOT, "scripts", "digest.py")).read()
        self.assertIn("learning.plan(LS, sorted(by_site), DAY, gaps", fc); self.assertIn("learning.record(LS, u, DAY", fc)
        self.assertIn("learning.plan(LS, [j[0] for j in jobs], d)", sw); self.assertIn("MAX_FAIL_RATE", sw); self.assertIn("MAX_NEW", sw)
        self.assertIn("learning.digest_lines", dg)
    def test_sweep_with_test_sources_does_not_touch_state(self):
        import sweep_daily
        before = os.path.exists(LR.STATE) and open(LR.STATE).read()
        r = sweep_daily.run(sources={"lists": [], "councils": []}, fetcher=lambda u: {"http": 404}, geocoder=lambda p: {}, write=False)
        self.assertIn("planned", r["learning"])
        self.assertEqual(before, os.path.exists(LR.STATE) and open(LR.STATE).read())

if __name__ == "__main__": unittest.main()
