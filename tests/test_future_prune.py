"""Learning scores unused for 90 days are forgotten, with a tombstone. The map is not touched."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning
from test_learning_guards import assert_schedule_and_guards

class Prune(unittest.TestCase):
    def test_schedule_and_floor_unchanged(self):
        assert_schedule_and_guards()
        self.assertEqual(learning.PRUNE_DAYS, 90)
        self.assertEqual(learning.FLOOR_DAYS, 7)
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.prune(LS, DAY, sites)", fc)
    def test_old_unseen_key_is_forgotten_and_starts_again(self):
        s = learning.load(os.devnull)
        learning.record(s, "https://old.test/", "2026-07-01", True, finds=3)
        learning.record(s, "https://keep.test/", "2026-07-01", True)
        learning.record(s, "https://recent.test/", "2026-10-20", True)
        learning.record(s, "https://undated.test/", "2026-01-01", True)
        s["keys"]["https://undated.test/"]["last_check"] = None
        learning.prune(s, "2026-10-26", ["https://keep.test/"])
        self.assertNotIn("https://old.test/", s["keys"])
        self.assertIn("https://keep.test/", s["keys"])
        self.assertIn("https://recent.test/", s["keys"])
        self.assertIn("https://undated.test/", s["keys"])
        self.assertEqual(s["tombstones"], [{"key": "https://old.test/", "last_day": "2026-07-01", "reason": "pruned"}])
        learning.record(s, "https://old.test/", "2026-10-26", True)
        self.assertEqual(s["keys"]["https://old.test/"]["checks"], 1)
    def test_empty_seen_prunes_nothing(self):
        s = learning.load(os.devnull)
        learning.record(s, "https://old.test/", "2026-01-01", True)
        learning.prune(s, "2026-10-26", [])
        self.assertIn("https://old.test/", s["keys"])
        self.assertNotIn("tombstones", s)

if __name__ == "__main__":
    unittest.main()
