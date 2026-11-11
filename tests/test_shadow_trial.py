"""Two-week shadow trial of the proposed Phase 2 rules (scripts/shadow_trial.py), record only.
Proves: nothing is written outside reports/shadow/; the refresh gate's items and files are byte-identical with the
trial on or off; a shadow error never fails or changes the refresh; results and the start date carry forward through
the private run-state restore; the trial records a 14-day window; and the four main workflows switch it on."""
import datetime, hashlib, json, os, shutil, sys, tempfile, unittest
from unittest import mock
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import discover as D, shadow_trial as ST, private_state_restore as PSR, intelligent_rails as IR
sys.path.insert(0, HERE)
import test_times_crosscheck_gate as G

R1, R2 = G.R1, G.R2
ON_ENV = {"HELPMAP_SHADOW_TRIAL": "1", "HELPMAP_STATE_RESTORED": "1"}
OFF_ENV = {"HELPMAP_SHADOW_TRIAL": "", "HELPMAP_STATE_RESTORED": "1"}


def tree(root, skip_shadow=True):
    out = {}
    for r, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(r, f); rel = os.path.relpath(p, root).replace(os.sep, "/")
            if skip_shadow and rel.startswith("reports/shadow/"): continue
            out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def gate_twice(root, env, page=None):
    IR.reset()
    f = G.fetch({"https://x.org/": G.pg(page or G.html())})
    with mock.patch.dict(os.environ, env):
        it = [G.item()]
        l1 = D.cross_check_times([dict(x) for x in it], "fb", "opening_times", f, state_root=root, rules=G.ON, run_at=R1)
        l2 = D.cross_check_times(it, "fb", "opening_times", f, state_root=root, rules=G.ON, run_at=R2)
    return it, l1, l2


class OnOff(unittest.TestCase):
    def test_gate_output_identical_with_trial_on_or_off(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            it_on, l1_on, l2_on = gate_twice(a, ON_ENV)
            it_off, l1_off, l2_off = gate_twice(b, OFF_ENV)
            self.assertEqual(json.dumps(it_on, sort_keys=True), json.dumps(it_off, sort_keys=True))
            self.assertEqual(json.dumps(l2_on, sort_keys=True, default=str), json.dumps(l2_off, sort_keys=True, default=str))
            self.assertEqual(tree(a), tree(b))                           # every non-shadow file byte-identical
            self.assertTrue(os.path.isdir(os.path.join(a, "reports", "shadow")))
            self.assertFalse(os.path.exists(os.path.join(b, "reports", "shadow")))
        finally:
            shutil.rmtree(a); shutil.rmtree(b)

    def test_held_change_identical_on_or_off(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            page = G.html(pc="ZZ9 9ZZ")                                   # postcode not on the page: held
            it_on, _, l_on = gate_twice(a, ON_ENV, page)
            it_off, _, l_off = gate_twice(b, OFF_ENV, page)
            self.assertEqual(json.dumps(it_on, sort_keys=True), json.dumps(it_off, sort_keys=True))
            self.assertEqual(tree(a), tree(b))
        finally:
            shutil.rmtree(a); shutil.rmtree(b)


class NoWritesOutside(unittest.TestCase):
    def test_only_reports_shadow_is_written(self):
        root = tempfile.mkdtemp()
        try:
            for rel, body in (("overrides/opening_times.json", "{}\n"), ("data.js", "x\n"), ("reports/times_auto_applied.json", "[]\n"),
                              ("logs/times_crosscheck_seen.json", "{}\n"), ("overrides/phones.json", "{}\n")):
                os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True); open(os.path.join(root, rel), "w").write(body)
            before = tree(root, skip_shadow=False)
            row = {"id": "a", "name": "A", "postcode": "AB1 2CD", "source_url": "https://x.org/", "host": "x.org", "new_structured": {"mon": [["10:00", "12:00"]]},
                   "old": G.OLD, "page_hash": "h", "days_on_page": ["mon"], "why_today": [], "today": "apply"}
            with mock.patch.dict(os.environ, ON_ENV):
                self.assertIsNotNone(ST.record("foodbanks", [row], root, run_at=R2))
            after = tree(root, skip_shadow=False)
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            self.assertTrue(changed)
            self.assertTrue(all(k.startswith("reports/shadow/") for k in changed), changed)
        finally:
            shutil.rmtree(root)

    def test_path_outside_shadow_refused(self):
        with self.assertRaises(ValueError): ST._safe_path("/tmp/x", "..", "..", "overrides", "phones.json")

    def test_nothing_recorded_without_restored_state(self):
        root = tempfile.mkdtemp()
        try:
            with mock.patch.dict(os.environ, {"HELPMAP_SHADOW_TRIAL": "1", "HELPMAP_STATE_RESTORED": ""}):
                self.assertIsNone(ST.record("foodbanks", [{"id": "a", "why_today": [], "today": "apply"}], root, run_at=R2))
            self.assertFalse(os.path.exists(os.path.join(root, "reports", "shadow")))
        finally:
            shutil.rmtree(root)

    def test_off_by_default(self):
        root = tempfile.mkdtemp()
        try:
            with mock.patch.dict(os.environ, {"HELPMAP_SHADOW_TRIAL": ""}):
                self.assertIsNone(ST.record("foodbanks", [{"id": "a", "why_today": [], "today": "apply"}], root, run_at=R2))
            self.assertEqual(os.listdir(root), [])
        finally:
            shutil.rmtree(root)


class FailClosed(unittest.TestCase):
    def test_shadow_errors_never_fail_or_change_the_gate(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            boom = mock.Mock(side_effect=RuntimeError("boom"))
            with mock.patch.object(ST, "snapshot", boom), mock.patch.object(ST, "_record", boom), mock.patch.object(ST, "note_failed_reads", boom):
                it_on, _, l_on = gate_twice(a, ON_ENV)
            it_off, _, l_off = gate_twice(b, OFF_ENV)
            self.assertEqual(json.dumps(it_on, sort_keys=True), json.dumps(it_off, sort_keys=True))
            self.assertEqual(tree(a), tree(b))
        finally:
            shutil.rmtree(a); shutil.rmtree(b)

    def test_record_swallows_errors(self):
        with mock.patch.dict(os.environ, ON_ENV), mock.patch.object(ST, "_record", side_effect=OSError("disk")):
            self.assertIsNone(ST.record("foodbanks", [{"id": "a"}], tempfile.mkdtemp(), run_at=R2))

    def test_finder_hook_is_fail_safe(self):
        with mock.patch.dict(os.environ, ON_ENV), mock.patch.object(ST, "snapshot", side_effect=RuntimeError("x")):
            buf = []; D._shadow_row(buf, {"id": "a"}, "opening_times", {}, None, {}, [])
            self.assertEqual(buf, [])
            D._shadow_done("sweep", [{"id": "a"}], None, R2, 0)       # no root: nothing, no raise


class CarryForward(unittest.TestCase):
    def test_results_and_start_date_survive_the_private_restore(self):
        run1, vault, run2 = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            row = {"id": "a", "name": "A", "host": "x.org", "source_url": "https://x.org/", "new_structured": {"thu": [["14:00", "16:00"]]},
                   "old": G.OLD, "page_hash": "h1", "days_on_page": ["thu"], "why_today": [], "today": "apply"}
            with mock.patch.dict(os.environ, ON_ENV):
                ST.record("foodbanks", [dict(row)], run1, run_at=R1)
            trial1 = json.load(open(os.path.join(run1, "reports", "shadow", "trial.json")))
            # private_state.sh save copies changed files under reports/ into site-run-state/<layer>/
            shutil.copytree(os.path.join(run1, "reports"), os.path.join(vault, "foodbanks", "reports"))
            open(os.path.join(vault, "foodbanks", ".saved_at"), "w").write("1")
            n, ok = PSR.restore(vault, run2)
            self.assertTrue(ok)
            self.assertEqual(json.load(open(os.path.join(run2, "reports", "shadow", "trial.json"))), trial1)
            with mock.patch.dict(os.environ, ON_ENV):
                ST.record("foodbanks", [dict(row)], run2, run_at=R2)
            mem = json.load(open(os.path.join(run2, "reports", "shadow", "foodbanks", "reads.json")))
            self.assertEqual(mem["foodbanks:a"]["n"], 2)                 # second identical read counted across runs
            self.assertEqual(json.load(open(os.path.join(run2, "reports", "shadow", "trial.json"))), trial1)
            day = json.load(open(os.path.join(run2, "reports", "shadow", "foodbanks", R2[:10] + ".json")))
            self.assertEqual([r["run_at"] for r in day["runs"]], [R1, R2])  # same day: both runs kept
        finally:
            for d in (run1, vault, run2): shutil.rmtree(d)

    def test_layers_write_separate_files(self):
        root = tempfile.mkdtemp()
        try:
            with mock.patch.dict(os.environ, ON_ENV):
                for layer in ("foodbanks", "shelters", "warmspaces", "sweep"):
                    ST.record(layer, [{"id": "a", "why_today": [], "today": "apply"}], root, run_at=R2)
            for layer in ("foodbanks", "shelters", "warmspaces", "sweep"):
                self.assertTrue(os.path.exists(os.path.join(root, "reports", "shadow", layer, R2[:10] + ".json")))
        finally:
            shutil.rmtree(root)


class TrialWindow(unittest.TestCase):
    def test_start_and_fourteen_day_end(self):
        root = tempfile.mkdtemp()
        try:
            t = ST.trial_state(root)
            s = datetime.date.fromisoformat(t["start"])
            self.assertEqual(t["start"], datetime.datetime.now(datetime.timezone.utc).date().isoformat())
            self.assertEqual(datetime.date.fromisoformat(t["last_day"]) - s, datetime.timedelta(days=13))
            self.assertEqual(datetime.date.fromisoformat(t["end"]) - s, datetime.timedelta(days=14))
            self.assertEqual(t["rules"], list(ST.RULES))
            json.dump(dict(t, start="2026-01-01"), open(os.path.join(root, "reports", "shadow", "trial.json"), "w"))
            self.assertEqual(ST.trial_state(root)["start"], "2026-01-01")  # never reset once recorded
        finally:
            shutil.rmtree(root)


class Rules(unittest.TestCase):
    def row(self, **kw):
        r = {"id": "a", "host": "x.org", "why_today": [], "today": "apply", "reads": {"n": 2}, "old": G.OLD,
             "new_structured": {"thu": [["14:00", "16:00"]]}, "days_on_page": ["thu"]}
        r.update(kw); return r

    def test_trust_only_tightens(self):
        d = ST._decide_trust({})
        self.assertEqual(d(self.row())[0], "hold")                       # unknown host: needs 3 reads
        self.assertEqual(d(self.row(reads={"n": 3}))[0], "apply")
        self.assertEqual(d(self.row(today="hold", why_today=["x"], reads={"n": 9}))[0], "hold")   # never loosens
        self.assertEqual(ST._decide_trust({"x.org": {"trusted": True}})(self.row())[0], "apply")

    def test_host_trust_needs_ten_applies_and_no_undo(self):
        root = tempfile.mkdtemp()
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log = [{"source_url": "https://x.org/p", "second_run_at": now} for _ in range(10)]
            log += [{"source_url": "https://y.org/p", "second_run_at": now} for _ in range(10)] + [{"source_url": "https://y.org/p", "second_run_at": now, "reverted": True}]
            os.makedirs(os.path.join(root, "reports")); json.dump(log, open(os.path.join(root, "reports", "times_auto_applied.json"), "w"))
            t = ST.host_trust(root)
            self.assertTrue(t["x.org"]["trusted"]); self.assertFalse(t["y.org"]["trusted"])
            self.assertEqual(ST.host_trust(tempfile.mkdtemp()), {})       # no memory: nobody trusted
        finally:
            shutil.rmtree(root)

    def test_cap_applies_strongest_up_to_room(self):
        cap = "blast limit: 50 auto-applies in foodbanks would pass 40; everything held for review"
        rows = [self.row(id=str(i), today="hold", why_today=[cap], reads={"n": i}) for i in range(5)]
        d = ST._decide_cap(rows, {}, 2, False)
        got = sorted(r["id"] for r in rows if d(r)[0] == "apply")
        self.assertEqual(got, ["3", "4"])
        self.assertTrue(all(ST._decide_cap(rows, {}, 2, True)(r)[0] == "hold" for r in rows))   # capped twice: brake

    def test_coverage_holds_failed_hosts_and_keeps_whole_layer_stop(self):
        cov = ["coverage gate: opened 15 of 19 source pages (79% < 80%)"]
        d = ST._decide_coverage({"source_pages": 19, "source_opened": 15}, {"bad.org"})
        self.assertEqual(d(self.row(today="hold", why_today=cov))[0], "apply")
        self.assertEqual(d(self.row(today="hold", why_today=cov, host="bad.org"))[0], "hold")
        d2 = ST._decide_coverage({"source_pages": 19, "source_opened": 5}, set())
        self.assertEqual(d2(self.row(today="hold", why_today=cov))[0], "hold")

    def test_fewer_days_needs_every_condition(self):
        why = ["would cut known hours to fewer days (drops Tue) and the source does not say that session ended; review"]
        trusted = {"x.org": {"trusted": True}}
        ok = {"n": 3, "first_run_at": "2026-11-01T00:00:00+00:00", "page_hash": "b", "page_hash_before": "a"}
        d = ST._decide_shrink(trusted, "2026-11-04T00:00:00+00:00")
        self.assertEqual(d(self.row(today="hold", why_today=why, reads=ok))[0], "apply")
        self.assertEqual(d(self.row(today="hold", why_today=why, reads=ok, days_on_page=["thu", "tue"]))[0], "hold")
        self.assertEqual(d(self.row(today="hold", why_today=why, reads=dict(ok, page_hash_before="b")))[0], "hold")
        self.assertEqual(d(self.row(today="hold", why_today=why, reads=dict(ok, n=2)))[0], "hold")
        self.assertEqual(ST._decide_shrink({}, "2026-11-04T00:00:00+00:00")(self.row(today="hold", why_today=why, reads=ok))[0], "hold")
        self.assertEqual(d(self.row(today="hold", why_today=why + ["postcode not matched exactly on the own-site page"], reads=ok))[0], "hold")


class Wiring(unittest.TestCase):
    def wf(self, name): return open(os.path.join(HERE, "..", ".github", "workflows", name), encoding="utf-8").read()

    def test_main_refreshes_and_sweep_switch_it_on(self):
        for name, cmd in (("refresh.yml", "python scripts/build.py"), ("refresh-shelters.yml", "python scripts/build_shelters.py"),
                          ("refresh-warmspaces.yml", "python scripts/build_warmspaces.py"), ("sweep-daily.yml", "python scripts/times_finder.py --render")):
            s = self.wf(name)
            step = s[s.rindex("- name:", 0, s.index(cmd)):]
            step = step[:step.index("- name:", 8)]
            self.assertIn('HELPMAP_SHADOW_TRIAL: "1"', step, name)
            self.assertIn("private_state.sh restore", s, name)              # results carried by the private run state
            self.assertNotIn("reports/shadow", s.replace("private reports/shadow/", ""), name)   # never staged

    def test_feed_finder_runs_weekly_and_fail_safe(self):
        s = self.wf("sweep-daily.yml")
        step = s[s.index("- name: Weekly council warm-space feed finder"):]
        step = step[:step.index("- name:", 8)]
        for need in ("python scripts/feed_finder.py", "continue-on-error: true", "timeout-minutes: 10", "github.ref == 'refs/heads/main'", "date -u +%u"):
            self.assertIn(need, step)
        src = open(os.path.join(HERE, "..", "scripts", "feed_finder.py"), encoding="utf-8").read()
        self.assertIn('OUT_JSON = "reports/official_source_proposals.json"', src)
        self.assertNotIn("open(FEEDS, \"w\"", src)

    def test_shadow_output_is_private(self):
        gi = open(os.path.join(HERE, "..", ".gitignore"), encoding="utf-8").read().split()
        self.assertIn("reports/", gi)
        self.assertEqual(ST.OUT, os.path.join("reports", "shadow"))


if __name__ == "__main__":
    unittest.main()
