"""The dry-run shows the real brake on the refresh files. It writes nothing and invents no count."""
import os, sys, json, hashlib, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, brake_dry_run as D
from test_learning_guards import assert_schedule_and_guards

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None

class DryRun(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        self.assertIn("learning.anomaly_brake", open(os.path.join(R, "scripts", "brake_dry_run.py"), encoding="utf-8").read())
    def test_repo_files_are_not_modified_and_the_decision_is_the_brake(self):
        watched = [os.path.join(R, "reports", p) for p in
                   ("daily_review.json", "access_changes.json", "learning_state.json", "anomaly_brake.md")]
        before = {p: sha(p) for p in watched}
        info = D.assess(R)
        self.assertEqual(before, {p: sha(p) for p in watched})
        self.assertFalse(info["published"]); self.assertFalse(info["wrote"])
        self.assertIsNone(before[os.path.join(R, "reports", "anomaly_brake.md")])
        text = D.report(info)
        self.assertIn("Nothing was published", text)
        if info["proposed"] is None:
            self.assertFalse(info["recorded"]["stop"])
            self.assertIn("no refresh run", info["recorded"]["reason"])
            return
        self.assertEqual(info["recorded"], learning.anomaly_brake(info["history"], info["proposed"]))
        self.assertEqual(info["live"], learning.anomaly_brake(info["live_change_counts"], info["proposed"]))
        self.assertIn(info["latest"]["at"], text)
        self.assertEqual(info["proposed"], info["latest"]["changes"])
        self.assertIsInstance(info["proposed"], int)
        for row in info["runs"]:
            self.assertGreaterEqual(row["changes"], 0)
    def test_a_short_history_invents_nothing(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            json.dump({"2026-10-27": {"date": "2026-10-27", "runs": [{"at": "2026-10-27T05:17:39+00:00", "flips": 40, "phone_fixes": 0, "closures": 0}]}},
                      open(os.path.join(d, "reports", "daily_review.json"), "w"))
            json.dump([{"when": "2026-10-27T05:17:39+00:00", "kind": "new food bank"} for _ in range(40)],
                      open(os.path.join(d, "reports", "access_changes.json"), "w"))
            info = D.assess(d)
            self.assertEqual(info["proposed"], 0)  # 40 new places are held for Dean; none were applied
            self.assertEqual(info["latest"]["held_new"], 40)
            self.assertEqual(len(info["history"]), 0)
            self.assertFalse(info["recorded"]["stop"])
            self.assertIn("not enough history", info["recorded"]["reason"])
            self.assertFalse(os.path.exists(os.path.join(d, "reports", "anomaly_brake.md")))
        finally:
            shutil.rmtree(d)
    def test_four_quiet_runs_then_a_spike_stops_on_the_same_rule(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            runs, changes = [], []
            for i, n in enumerate((2, 2, 2, 2, 20)):
                at = "2026-10-2%dT05:00:00+00:00" % (3 + i)
                runs.append({"at": at, "flips": n, "phone_fixes": 0, "closures": 0})
                changes += [{"when": at, "kind": "phone"} for _ in range(n)]
            json.dump({"2026-10-27": {"date": "2026-10-27", "runs": runs}},
                      open(os.path.join(d, "reports", "daily_review.json"), "w"))
            json.dump(changes, open(os.path.join(d, "reports", "access_changes.json"), "w"))
            json.dump({"version": 1, "change_counts": [{"day": "2026-10-23", "changes": 2}] * 4},
                      open(os.path.join(d, "reports", "learning_state.json"), "w"))
            info = D.assess(d)
            self.assertEqual(info["proposed"], 20)
            self.assertEqual([h["changes"] for h in info["history"]], [2, 2, 2, 2])
            self.assertTrue(info["recorded"]["stop"])
            self.assertEqual(info["recorded"]["median"], 2)
            self.assertTrue(info["live"]["stop"])
            self.assertIn("STOP", D.report(info))
            self.assertIn("Nothing was published", D.report(info))
            self.assertFalse(os.path.exists(os.path.join(d, "reports", "anomaly_brake.md")))
            quiet = learning.anomaly_brake(info["history"], 9)
            self.assertFalse(quiet["stop"])
        finally:
            shutil.rmtree(d)
    def test_eleven_held_new_places_do_not_stop_twelve_applied_does(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "reports"))
            runs, changes = [], []
            for i in range(4):
                at = "2026-10-2%dT05:00:00+00:00" % (3 + i)
                runs.append({"at": at, "flips": 2, "phone_fixes": 0, "closures": 0})
                changes += [{"when": at, "kind": "phone", "old": "1", "new": "2"} for _ in range(2)]
            at = "2026-10-27T05:17:39+00:00"
            runs.append({"at": at, "flips": 0, "phone_fixes": 2, "closures": 0})
            changes += [{"when": at, "kind": "new food bank", "id": "n%d" % i} for i in range(11)]
            changes += [{"when": at, "kind": "phone", "old": "1", "new": "2"}, {"when": at, "kind": "removed", "id": "gone"}]
            json.dump({"2026-10-27": {"runs": runs}}, open(os.path.join(d, "reports", "daily_review.json"), "w"))
            json.dump(changes, open(os.path.join(d, "reports", "access_changes.json"), "w"))
            info = D.assess(d)
            self.assertEqual(info["proposed"], 2)
            self.assertEqual(info["latest"]["held_new"], 11)
            self.assertEqual(info["recorded"]["median"], 2)
            self.assertFalse(info["recorded"]["stop"])
            self.assertFalse(os.path.exists(os.path.join(d, "reports", "anomaly_brake.md")))
            at12 = "2026-10-28T05:00:00+00:00"
            runs.append({"at": at12, "flips": 12, "phone_fixes": 0, "closures": 0})
            changes += [{"when": at12, "old": "voucher", "new": "walkin"} for _ in range(12)]
            json.dump({"2026-10-28": {"runs": runs}}, open(os.path.join(d, "reports", "daily_review.json"), "w"))
            json.dump(changes, open(os.path.join(d, "reports", "access_changes.json"), "w"))
            again = D.assess(d)
            self.assertEqual(again["proposed"], 12)
            self.assertEqual(again["recorded"]["median"], 2)
            self.assertTrue(again["recorded"]["stop"])
        finally:
            shutil.rmtree(d)

if __name__ == "__main__":
    unittest.main()
