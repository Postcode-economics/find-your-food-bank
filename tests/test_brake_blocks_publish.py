"""Anomaly brake (review of PR #243): opening-times changes the refresh gate applied count towards the brake, and a stop
really blocks the publish. full_check.py runs continue-on-error, so the stop is a step output that fails a later step
in refresh.yml before the commit step. The anomaly_brake.md wording must match what happens."""
import json, os, shutil, subprocess, sys, tempfile, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import full_check as F, learning


def entry(i, **kw):
    return dict({"id": i, "kind": "fb", "path": "cross_check", "old": None, "new": {"structured": {"tue": [["10:00", "12:00"]]}},
                 "source_url": "https://x.example/", "revert": "python scripts/times_revert.py fb:" + i}, **kw)


class GateTimesCount(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "reports"))
        self.log = os.path.join(self.d, "reports", "times_auto_applied.json")
    def git(self, *a): subprocess.run(["git", *a], cwd=self.d, check=True, capture_output=True)

    def test_only_entries_newer_than_the_published_commit_count(self):
        self.git("init", "-q"); self.git("config", "user.email", "t@t"); self.git("config", "user.name", "t")
        old = entry("a"); json.dump([old, entry("b")], open(self.log, "w")); self.git("add", "-A"); self.git("commit", "-qm", "base")
        json.dump([old, entry("b", reverted=True), entry("c"), entry("d"), dict(entry("e"), path=None)], open(self.log, "w"))
        self.assertEqual([e["id"] for e in F.gate_applied_times(self.d)], ["c", "d"])   # not a revert, not a finder entry

    def test_no_published_copy_counts_nothing_and_does_not_crash(self):
        json.dump([entry("a")], open(self.log, "w"))
        self.assertEqual(F.gate_applied_times(self.d), [])
        self.assertEqual(F.gate_applied_times(os.path.join(self.d, "missing")), [])


class MainStopsOnCombinedCount(unittest.TestCase):
    """12 refresh-gate times changes against a median of 2: stop, nothing written.
    The 4 clear phone proposals in the same run are held and do not count. The same run with no gate times does not stop."""
    def run_main(self, gate_times, dry=False):
        sites = ["https://s%02d.example/home" % n for n in range(4)]
        items = [dict(id="bb-%02d" % n, type="foodbank", name="B%d" % n, foodbank="B%d" % n, website=u, phone="01000000000", tel="01000000000")
                 for n, u in enumerate(sites)]
        phone = ["02000000000"]
        store = {"full_check_state.json": {"sites": {u: {"phones": phone, "tel": phone, "final_url": u + "/contact",
                                                           "checked_at": "2026-10-27T03:00:00+00:00", "access": "unclear"} for u in sites},
                                           "ids": [i["id"] for i in items]}}
        LS = learning.load(path=os.path.join(tempfile.mkdtemp(), "none.json")); LS["change_counts"] = [{"day": "d%d" % n, "changes": 2} for n in range(4)]
        written, saved = {}, []
        rep, tmp = tempfile.mkdtemp(), tempfile.mkdtemp(); out = os.path.join(tmp, "gh_output"); self.tmp = tmp
        def fake(u):
            return dict(url=u, ok=True, final_url=u + "/contact", pages=[u + "/contact"], access="unclear", hours_hash="", hours_sample=[],
                        seasonal=None, closed=None, perm_closed=None, phones=phone, tel=phone, needs=None, checked_at="2026-10-27T11:00:00+00:00", http=200)
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.gate_applied_times, F.DATA, F.ACC, learning.load, learning.save)
        F.DATA = os.path.join(tmp, "data.full.js"); F.ACC = os.path.join(tmp, "access.js")
        F.rj = lambda n, d: store.get(n, d); F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ("x=", {"items": items}); F.load_access = lambda: {}
        F.write_md = lambda *a: None; F.REP = rep; F.check_site = fake
        F.gate_applied_times = lambda root=None: [entry("t%d" % n) for n in range(gate_times)]
        learning.load = lambda *a, **k: LS
        learning.save = lambda s, *a, **k: saved.append(json.loads(json.dumps(s)))
        env = {k: os.environ.get(k) for k in ("DRY_RUN", "SAMPLE", "GITHUB_OUTPUT")}
        os.environ.pop("DRY_RUN", None); os.environ.pop("SAMPLE", None); os.environ["GITHUB_OUTPUT"] = out
        if dry: os.environ["DRY_RUN"] = "1"   # the run that goes ahead must not write data files from a test
        try: F.main()
        finally:
            (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.gate_applied_times, F.DATA, F.ACC, learning.load, learning.save) = orig
            for k, v in env.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        return items, written, saved, rep, open(out).read()

    def test_gate_times_push_the_run_over_the_bar_and_block_it(self):
        items, written, saved, rep, out = self.run_main(12)
        self.assertEqual(out, "brake=stop\n")
        md = open(os.path.join(rep, "anomaly_brake.md"), encoding="utf-8").read()
        self.assertIn("would change 12 places", md)
        self.assertIn("Counted: 0 own-site changes", md); self.assertIn("12 opening-times changes the refresh gate applied", md)
        self.assertIn("fails at its anomaly brake step, before the commit step", md)
        self.assertNotIn("phone_fixes.json", written); self.assertEqual({i["phone"] for i in items}, {"01000000000"})
        for f in ("access_changes.json", "access_tags.json", "full_check_state.json", "provenance.json"):
            self.assertNotIn(f, written)
        self.assertEqual(os.listdir(self.tmp), ["gh_output"])   # no data.full.js or access.js
        self.assertEqual(saved[-1]["change_counts"], [{"day": "d%d" % n, "changes": 2} for n in range(4)])   # the spike is not a new baseline
        self.assertTrue(saved[-1]["anomaly"]["stop"])
        self.assertEqual(saved[-1]["anomaly"]["proposed"], 12)

    def test_without_gate_times_the_same_run_goes_ahead(self):
        items, written, saved, rep, out = self.run_main(0, dry=True)
        self.assertEqual(out, "brake=ok\n")
        self.assertFalse(os.path.exists(os.path.join(rep, "anomaly_brake.md")))


class WorkflowBlocks(unittest.TestCase):
    def test_a_stop_fails_a_step_before_the_commit(self):
        w = open(os.path.join(R, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
        full = w.index("run: python scripts/full_check.py")
        self.assertIn("id: full", w[w.rindex("- name:", 0, full):full])
        stop = w.index("if: steps.full.outputs.brake == 'stop'")
        step = w[w.rindex("- name:", 0, stop):w.index("- name:", stop)]
        self.assertIn("exit 1", step); self.assertNotIn("continue-on-error", step)
        commit = w.index("id: commit")
        self.assertLess(full, stop); self.assertLess(stop, commit)
        cstep = w[w.rindex("- name:", 0, commit):w.index("run: |", commit)]
        self.assertNotIn("if:", cstep)   # a failed step before it skips the commit
        self.assertIn("if: (failure() || cancelled()) && steps.commit.outcome != 'success'", w)   # and the 'nothing published' alert opens


if __name__ == "__main__":
    unittest.main()
