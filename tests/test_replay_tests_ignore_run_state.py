"""The 29 Oct / 5 Nov replay tests read their historical records only from the private vault copy
(HELPMAP_PRIVATE_REPLAY_ROOT), never from the checkout's reports/times_auto_applied.json. Since #491 that file is the
run's own private run state (restored from the vault, then appended to by the refresh gate), so on 10 Nov every
practice whose refresh gate applied a time failed the post-rebuild test step on records that file never holds.
Synthetic data only (rule 97)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODS = ("test_times_crosscheck_oct29_eighteen.py", "test_doorway_hours_lock.py")
WRONG = {"fri": [["09:00", "16:30"]]}
DOORWAY = "man-doorway-young-people-16-25"


def fresh_apply(iid="synthetic-1", kind="ws", **kw):
    e = {"id": iid, "kind": kind, "path": "cross_check", "name": "Synthetic place", "old": None,
         "new": {"raw": "Mon 10:00 - 12:00"}, "new_structured": {"mon": [["10:00", "12:00"]]},
         "second_run_at": "2026-11-10T10:40:00+00:00", "source_url": "https://example.org/hours"}
    e.update(kw); return e


class ReplayTestsIgnoreRunState(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "tests"))
        for m in MODS: shutil.copyfile(os.path.join(ROOT, "tests", m), os.path.join(self.d, "tests", m))
        for n in ("scripts", "overrides", "shelters.js"): os.symlink(os.path.join(ROOT, n), os.path.join(self.d, n))
        os.makedirs(os.path.join(self.d, "reports"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, root, entries):
        os.makedirs(os.path.join(root, "reports"), exist_ok=True)
        json.dump(entries, open(os.path.join(root, "reports", "times_auto_applied.json"), "w"))

    def run_mods(self, **env):
        e = dict(os.environ); e.pop("HELPMAP_PRIVATE_REPLAY_ROOT", None); e.update(env)
        return subprocess.run([sys.executable, "-m", "unittest", "-v", *[m[:-3] for m in MODS]],
                              cwd=os.path.join(self.d, "tests"), env=e, capture_output=True, text=True, timeout=120)

    def test_run_state_log_without_the_historical_records_passes(self):
        # what a refresh run looks like after its gate applied a fresh time: the log exists, the 29 Oct records don't
        self.write(self.d, [fresh_apply(), fresh_apply(DOORWAY, "sh", new_structured=WRONG, reverted=True)])
        r = self.run_mods()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Private replay report is not available", r.stderr)

    def test_run_state_log_with_a_live_wrong_doorway_apply_still_fails(self):
        self.write(self.d, [fresh_apply(DOORWAY, "sh", new_structured=WRONG)])
        r = self.run_mods()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("test_run_state_log_never_holds_a_live_wrong_apply", r.stderr)

    def test_replay_copy_missing_the_records_still_fails(self):
        # the replays are not weakened: pointed at a historical copy that lacks the records, they fail as before
        replay = os.path.join(self.d, "replay"); self.write(replay, [fresh_apply()])
        r = self.run_mods(HELPMAP_PRIVATE_REPLAY_ROOT=replay)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("test_apply_log_marked_reverted", r.stderr)
        self.assertIn("StopIteration", r.stderr)


if __name__ == "__main__": unittest.main()
