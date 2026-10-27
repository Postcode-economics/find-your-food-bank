"""Stop a run that would change far more places than recent runs. No history, no stop."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning
from test_learning_guards import assert_schedule_and_guards

class Anomaly(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.anomaly_brake(LS.get('change_counts')", fc)
        self.assertIn("Nothing from this run was published", fc)
    def test_needs_history_and_stops_only_on_a_real_spike(self):
        quiet = learning.anomaly_brake([], 50)
        self.assertFalse(quiet["stop"]); self.assertIn("not enough history", quiet["reason"])
        short = learning.anomaly_brake([{"changes": 1}, {"changes": 2}, {"changes": 1}], 40)
        self.assertFalse(short["stop"])
        usual = [{"day": "2026-10-0%d" % i, "changes": 2} for i in (1, 2, 3, 4)]
        self.assertFalse(learning.anomaly_brake(usual, 9)["stop"])
        stopped = learning.anomaly_brake(usual, 20)
        self.assertTrue(stopped["stop"]); self.assertIn("Stopped and flagged", stopped["reason"])
        self.assertEqual(stopped["median"], 2)
    def test_a_stop_does_not_grant_an_add_or_a_removal(self):
        import auto_rules
        rules = auto_rules.load()
        self.assertFalse(learning.allow_under_rules("new_place", rules, 1, "foodbanks"))
        self.assertFalse(learning.allow_under_rules("remove_place", rules, 1))
    def test_held_new_places_do_not_stop_and_twelve_applied_does(self):
        """11 new places held for Dean plus 2 applied changes stay under the bars.
        12 applied changes against a median of 2 stop. The bars themselves are unchanged."""
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.applied_count(this_run)", fc)
        self.assertIn("{'day': DAY, 'changes': n_applied}", fc)
        usual = [{"day": "2026-10-0%d" % i, "changes": 2} for i in (1, 2, 3, 4)]
        self.assertEqual(learning.anomaly_brake(usual, 2)["median"], 2)
        held = [{"kind": "new food bank", "id": "n%d" % i, "old": "not on map", "new": "added"} for i in range(11)]
        two = [{"kind": "phone", "old": "01000000000", "new": "02000000000"}, {"kind": "removed", "id": "gone"}]
        self.assertEqual(learning.applied_count(held + two), 2)
        quiet = learning.anomaly_brake(usual, learning.applied_count(held + two))
        self.assertFalse(quiet["stop"])
        self.assertEqual(quiet["median"], 2)
        self.assertIn("within the usual range (2 vs about 2)", quiet["reason"])
        dozen = ([{"old": "voucher", "new": "walkin"} for _ in range(6)]
                 + [{"kind": "phone", "old": "1", "new": "2"} for _ in range(3)]
                 + [{"kind": "hours", "old": "10:00", "new": "11:00"} for _ in range(2)]
                 + [{"kind": "removed", "id": "r"}])
        self.assertEqual(learning.applied_count(dozen), 12)
        stopped = learning.anomaly_brake(usual, learning.applied_count(dozen))
        self.assertTrue(stopped["stop"])
        self.assertEqual(stopped["median"], 2)
        self.assertEqual(stopped["proposed"], 12)
        self.assertFalse(learning.anomaly_brake(usual, 9)["stop"])
        self.assertTrue(learning.anomaly_brake(usual, 10)["stop"])

if __name__ == "__main__": unittest.main()
