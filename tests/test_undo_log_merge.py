"""Automatic-change undo logs and two-run state are written by several refresh workflows. When two runs overlap, the
rebase must keep every undo entry from both sides once (never this run's copy over main's), keep reverted entries
reverted, and merge the seen/undone maps key by key. The same change seen again on later runs is logged once."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rebase_resolve as rr
import times_finder as TF

A = {"id": "fb/a", "kind": "fb", "path": "cross_check", "new_structured": {"wed": [["09:00", "11:00"]]}, "source_url": "https://a.org/", "revert": "python scripts/times_revert.py fb:a"}
B = {"id": "ws:b", "kind": "ws", "path": "cross_check", "new_structured": {"thu": [["14:00", "16:00"]]}, "source_url": "https://b.org/", "revert": "python scripts/times_revert.py ws:b"}
C = {"id": "sh:c", "kind": "sh", "path": "cross_check", "new_structured": {"fri": [["10:00", "12:00"]]}, "source_url": "https://c.org/", "revert": "python scripts/times_revert.py sh:c"}
J = json.dumps


def g(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *a], cwd=cwd, check=check, capture_output=True, text=True)


class MergeFunctions(unittest.TestCase):
    def test_undo_log_is_a_union_with_no_duplicates(self):
        out = rr.merge_undo_log(J([A]), J([A, B]), J([A, C]))
        self.assertEqual(out, [A, B, C])
        self.assertEqual(rr.merge_undo_log(J([A]), J([A]), J([A])), [A])

    def test_a_revert_on_either_side_stays(self):
        rev = dict(A, reverted=True)
        self.assertEqual(rr.merge_undo_log(J([A]), J([rev]), J([A, C])), [rev, C])
        self.assertEqual(rr.merge_undo_log(J([A]), J([A, B]), J([rev])), [rev, B])

    def test_unreadable_side_does_not_drop_the_other(self):
        self.assertEqual(rr.merge_undo_log(None, "not json", J([A])), [A])
        self.assertEqual(rr.merge_undo_log(None, J([A]), None), [A])

    def test_keyed_map_three_way(self):
        base = {"fb:a": {"sig": "1", "run_at": "r1"}, "ws:b": {"sig": "2", "run_at": "r1"}, "sh:c": {"sig": "3", "run_at": "r1"}}
        main = dict(base, **{"ws:b": {"sig": "2", "run_at": "r2"}, "ws:n": {"sig": "9", "run_at": "r2"}})
        run = {k: v for k, v in base.items() if k != "sh:c"}
        run["fb:a"] = {"sig": "1", "run_at": "r3"}
        out = rr.merge_keyed(J(base), J(main), J(run))
        self.assertEqual(out["fb:a"], {"sig": "1", "run_at": "r3"})   # the run's change
        self.assertEqual(out["ws:b"], {"sig": "2", "run_at": "r2"})   # main's change, untouched by the run
        self.assertEqual(out["ws:n"], {"sig": "9", "run_at": "r2"})   # main's new key
        self.assertNotIn("sh:c", out)                                  # the run dropped it and main left it alone

    def test_every_shared_state_file_is_marked_for_the_json_merge(self):
        attrs = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read().split("\n")
        for f in sorted(rr.UNDO_LOGS | rr.KEYED):
            self.assertIn(f + " -merge", attrs, f)


class RebaseRace(unittest.TestCase):
    def setUp(self):
        if not shutil.which("git"): self.skipTest("git missing")
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        origin = os.path.join(self.d, "origin.git")
        g(self.d, "init", "-q", "--bare", "-b", "main", origin)
        self.main = self._clone(origin, "main")
        os.makedirs(os.path.join(self.main, "scripts")); os.makedirs(os.path.join(self.main, "reports")); os.makedirs(os.path.join(self.main, "logs"))
        for f in ("refresh_rebase_conflicts.sh", "rebase_resolve.py"):
            shutil.copy(os.path.join(ROOT, "scripts", f), os.path.join(self.main, "scripts", f))
        shutil.copy(os.path.join(ROOT, ".gitattributes"), self.main)
        self._w(self.main, "reports/times_auto_applied.json", J([A], indent=1))
        self._w(self.main, "logs/times_crosscheck_seen.json", J({"fb:a": {"sig": "1", "run_at": "r1"}}))
        g(self.main, "add", "-A"); g(self.main, "commit", "-q", "-m", "base"); g(self.main, "push", "-q", "origin", "main")
        self.run_ = self._clone(origin, "run")

    def _clone(self, origin, name):
        p = os.path.join(self.d, name)
        g(self.d, "clone", "-q", origin, p); g(p, "config", "user.email", "t@t"); g(p, "config", "user.name", "t")
        return p

    def _w(self, repo, f, s):
        with open(os.path.join(repo, f), "w", encoding="utf-8") as fh: fh.write(s + "\n")

    def _r(self, repo, f):
        return json.load(open(os.path.join(repo, f), encoding="utf-8"))

    def test_overlapping_runs_keep_both_sides_undo_entries(self):
        # warm-spaces run lands first: logs B and refreshes its seen row
        self._w(self.main, "reports/times_auto_applied.json", J([A, B], indent=1))
        self._w(self.main, "logs/times_crosscheck_seen.json", J({"fb:a": {"sig": "1", "run_at": "r1"}, "ws:b": {"sig": "2", "run_at": "r2"}}))
        g(self.main, "commit", "-qam", "warm spaces refresh"); g(self.main, "push", "-q")
        # shelters run started earlier, from the base: logs C
        self._w(self.run_, "reports/times_auto_applied.json", J([A, C], indent=1))
        self._w(self.run_, "logs/times_crosscheck_seen.json", J({"fb:a": {"sig": "1", "run_at": "r1"}, "sh:c": {"sig": "3", "run_at": "r3"}}))
        g(self.run_, "commit", "-qam", "shelters refresh")
        r = g(self.run_, "pull", "-q", "--rebase", check=False)
        self.assertNotEqual(r.returncode, 0, "expected the -merge attribute to make this a conflict")
        shim = os.path.join(self.d, "bin"); os.makedirs(shim)
        os.symlink(sys.executable, os.path.join(shim, "python"))   # the workflow's 'python'
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
        out = subprocess.run(["bash", "scripts/refresh_rebase_conflicts.sh"], cwd=self.run_, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("json-merge", out.stdout)
        g(self.run_, "-c", "core.editor=true", "rebase", "--continue")
        self.assertEqual(self._r(self.run_, "reports/times_auto_applied.json"), [A, B, C])
        self.assertEqual(set(self._r(self.run_, "logs/times_crosscheck_seen.json")), {"fb:a", "ws:b", "sh:c"})
        self.assertEqual(g(self.run_, "status", "--porcelain").stdout, "")


class FinderLogsOnce(unittest.TestCase):
    GOOD = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
            "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27"}
    ITEM = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
    def setUp(self):
        self.old = os.getcwd(); self.d = tempfile.mkdtemp(); os.chdir(self.d)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        self.ks = TF.known; TF.known = lambda: {"pages": {}, "skip": {}}
    def tearDown(self):
        os.chdir(self.old); TF.known = self.ks; shutil.rmtree(self.d, True)
    def test_same_finder_change_on_later_runs_is_one_undo_entry(self):
        runs = ("2026-10-26T19:05:00+00:00", "2026-10-27T03:05:00+00:00", "2026-10-27T11:05:00+00:00", "2026-10-27T19:05:00+00:00")
        for n, now in enumerate(runs):
            log = {"found": {"fb1": dict(self.GOOD)}}
            TF.decide(log, [dict(self.ITEM)], False, rules={"times_auto_apply": True}, now=now)
            self.assertEqual(log["applied"], ["fb1"] if n else [])
        auto = json.load(open(TF.AUTO_LOG))
        self.assertEqual(len(auto), 1, auto)
        self.assertEqual((auto[0]["first_run_at"], auto[0]["second_run_at"]), runs[:2])
        self.assertEqual(auto[0]["revert"], "python scripts/times_revert.py fb1")
    def test_a_different_table_later_is_a_new_entry(self):
        for now, wed in (("2026-10-26T19:05:00+00:00", "10:00"), ("2026-10-27T03:05:00+00:00", "10:00"),
                         ("2026-10-27T11:05:00+00:00", "11:00"), ("2026-10-27T19:05:00+00:00", "11:00")):
            ot = dict(self.GOOD, structured={"wed": [[wed, "12:00"]]})
            TF.decide({"found": {"fb1": ot}}, [dict(self.ITEM)], False, rules={"times_auto_apply": True}, now=now)
        self.assertEqual([e["new"]["structured"] for e in json.load(open(TF.AUTO_LOG))],
                         [{"wed": [["10:00", "12:00"]]}, {"wed": [["11:00", "12:00"]]}])


if __name__ == "__main__":
    unittest.main()
