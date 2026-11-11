"""Weekly self-sufficiency scorecard (plan 0.2): private, real data only, fails closed, never blocks a run.

Locks in: counts come only from the saved run-state files (missing input = null / "no data yet", never a number);
the card is written only under reports/scorecard/ (ignored by git, rule 97) and refused anywhere else; no saved state
means nothing is written; any error exits 0; the weekly switch writes once per ISO week on Sundays; week-on-week uses
last week's card; and the deep sweep calls it on main after its commit, before the private save, without the state key."""
import datetime, io, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scorecard as S

try:
    import yaml
except ImportError:  # same as the other workflow guard tests: the refresh runners start without pyyaml
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

UTC = datetime.timezone.utc
SUNDAY = datetime.datetime(2026, 11, 15, 3, 30, tzinfo=UTC)      # 2026-W46


def put(base, rel, obj):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "site-run-state")
        self.root = os.path.join(self.d, "checkout")
        os.makedirs(self.root)
        s = self.state
        put(s, "foodbanks/reports/times_auto_applied.json", [
            {"id": "a", "kind": "fb", "path": "cross_check", "second_run_at": "2026-11-10T05:52:54+00:00"},
            {"id": "b", "kind": "fb", "path": "cross_check", "second_run_at": "2026-11-12T05:52:54+00:00", "reverted": True},
            {"id": "old", "kind": "fb", "path": "cross_check", "second_run_at": "2026-11-02T05:52:54+00:00"},
            {"id": "f1", "second_run_at": "2026-11-11T03:40:00+00:00"}])
        put(s, "shelters/reports/times_auto_applied.json", [
            {"id": "s1", "kind": "sh", "path": "cross_check", "second_run_at": "2026-11-11T04:50:00+00:00"},
            {"id": "a", "kind": "fb", "path": "cross_check", "second_run_at": "2026-11-10T05:52:54+00:00", "reverted": True}])
        put(s, "foodbanks/reports/intelligent_mode.json", {"run": "2026-11-14", "would_block": [], "layers": {"foodbanks": {
            "held": 3, "applied": 1, "stale_cleared": 0, "errors": [],
            "rejected": [{"id": "x", "reasons": ["own site lists several centres (10 postcodes); cannot tie"]},
                         {"id": "y", "reasons": ["own site lists several centres (3 postcodes)"]}],
            "coverage": {"sites": 17, "sites_opened": 15, "source_pages": 19, "source_opened": 16}}}})
        put(s, "warmspaces/logs/pending_dean.json", {"foodbanks": [], "warmspaces": [
            {"id": "w1", "why": ["no verified phone"]}, {"id": "w2", "why": ["no verified phone"]}]})
        put(s, "sweep/logs/follow_through_queue_seen.json", {"q1": "2026-11-11", "q2": "2026-11-01"})
        put(s, "foodbanks/reports/learning_state.json", {"change_counts": [{"day": "2026-11-10", "changes": 6},
                                                                            {"day": "2026-11-03", "changes": 99}]})
        put(s, "foodbanks/.saved_at", "1794409992")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def card(self, prev=None):
        return S.build(self.state, "2026-W46", prev=prev, now=SUNDAY, gh={l: None for l in S.LAYERS})


class Counts(Fixture):
    def test_auto_applied_this_week_per_layer_with_undone_union(self):
        c = self.card()["layers"]
        self.assertEqual(c["foodbanks"]["auto_applied_this_week"], 2)   # a and b; 'old' is last week
        self.assertEqual(c["foodbanks"]["undone_of_those"], 2)          # b, and a reverted in another layer's copy
        self.assertEqual(c["shelters"]["auto_applied_this_week"], 1)
        self.assertEqual(c["sweep"]["auto_applied_this_week"], 1)       # times_finder entry (no path)
        self.assertEqual(c["warmspaces"]["auto_applied_this_week"], 0)
        self.assertIsNone(c["warmspaces"]["undo_rate"])                 # nothing applied: no rate is made up

    def test_held_reasons_grouped_and_unreachable_counted(self):
        ld = self.card()["layers"]["foodbanks"]["latest_day"]
        self.assertEqual(ld["held"], 3)
        self.assertEqual(ld["hold_reasons"], {"own site lists several centres": 2})
        self.assertEqual(ld["unreachable"]["sites_not_opened"], 2)
        self.assertEqual(ld["unreachable"]["source_pages_not_opened"], 3)

    def test_missing_inputs_are_null_and_no_data_yet(self):
        c = self.card()
        self.assertIsNone(c["layers"]["shelters"]["latest_day"])
        self.assertIsNone(c["layers"]["shelters"]["pending"])
        self.assertIsNone(c["shadow_trial"])
        self.assertIsNone(c["foodbank_page_failures"])
        self.assertIsNone(c["week_on_week"])
        md = S.render(c)
        self.assertIn("no data yet", md)
        self.assertIn("first scorecard, so no data yet", md)
        self.assertNotIn("verified", md.replace("hand-verified", "").replace("no verified phone", ""))

    def test_follow_through_and_brake(self):
        c = self.card()
        self.assertEqual(c["discovery"]["follow_through"], {"followed_up_this_week": 1, "tracked": 2})
        self.assertEqual(c["brake"]["runs_counted_this_week"], 1)
        self.assertEqual(c["brake"]["max_changes_in_a_run"], 6)
        self.assertEqual(c["brake"]["trips_this_week"], 0)

    def test_week_on_week_and_queue_age(self):
        prev = json.loads(json.dumps(self.card()))
        prev["week"] = "2026-W45"
        prev["layers"]["warmspaces"]["pending"]["ids"] = ["w1"]
        prev["layers"]["foodbanks"]["latest_day"]["held"] = 5
        prev["layers"]["foodbanks"]["latest_day"]["held_ids"] = ["a", "zz"]
        c = self.card(prev)
        self.assertEqual(c["layers"]["warmspaces"]["pending"]["also_at_last_scorecard"], 1)
        self.assertEqual(c["week_on_week"]["change"]["foodbanks"]["held_latest_day"], -2)
        self.assertEqual(c["layers"]["foodbanks"]["held_at_last_card_auto_applied_since"], 1)
        self.assertEqual(c["layers"]["foodbanks"]["held_at_last_card"], 2)

    def test_shadow_trial_read_when_recorded(self):
        put(self.state, "shelters/reports/shadow/trial.json", {"start": "2026-11-12", "last_day": "2026-11-25", "end": "2026-11-26"})
        put(self.state, "shelters/reports/shadow/shelters/2026-11-13.json", {"runs": [
            {"candidates": 4, "rules": {"2.1-per-item-cap": {"differs_from_today": [{"id": "s"}]}, "2.4-fewer-days": {"differs_from_today": []}}}]})
        sh = self.card()["shadow_trial"]
        self.assertEqual(sh["trial"]["start"], "2026-11-12")
        self.assertEqual(sh["layers"]["shelters"], {"runs": 1, "candidates": 4, "differs_by_rule": {"2.1-per-item-cap": 1, "2.4-fewer-days": 0}})

    def test_github_runs_counted_and_none_without_token(self):
        start, end = S.week_bounds("2026-W46")
        self.assertEqual(S.runs(start, end, token=""), {l: None for l in S.LAYERS})
        body = json.dumps({"workflow_runs": [{"conclusion": "success"}, {"conclusion": "failure"}, {"conclusion": None, "status": "in_progress"}]}).encode()
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        got = S.runs(start, end, token="t", repo="o/r", opener=lambda req, timeout=None: R(body))
        self.assertEqual(got["sweep"], {"runs": 3, "success": 1, "failure": 1, "other": 1})
        def boom(req, timeout=None): raise OSError("offline")
        self.assertEqual(S.runs(start, end, token="t", repo="o/r", opener=boom)["foodbanks"], None)


class Writes(Fixture):
    def files(self):
        out = []
        for d, _, fs in os.walk(self.root):
            out += [os.path.relpath(os.path.join(d, f), self.root) for f in fs]
        return sorted(out)

    def test_writes_only_reports_scorecard(self):
        self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
        self.assertEqual(self.files(), ["reports/scorecard/2026-W46.json", "reports/scorecard/2026-W46.md"])

    def test_no_state_writes_nothing(self):
        self.assertEqual(S.main(["--state", os.path.join(self.d, "missing"), "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
        self.assertEqual(self.files(), [])

    def test_refuses_a_write_that_escapes_reports(self):
        os.makedirs(os.path.join(self.root, "reports"))
        os.symlink(os.path.join(self.d, "elsewhere"), os.path.join(self.root, "reports", "scorecard"))
        with self.assertRaises(ValueError):
            S.safe_out(self.root)
        self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
        self.assertFalse(os.path.exists(os.path.join(self.d, "elsewhere")))

    def test_any_error_exits_zero(self):
        self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "not-a-week"], now=SUNDAY), 0)
        with mock.patch.object(S, "build", side_effect=RuntimeError("x")):
            self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
        self.assertEqual(self.files(), [])

    def test_weekly_sunday_once(self):
        monday = datetime.datetime(2026, 11, 16, 3, 30, tzinfo=UTC)
        S.main(["--weekly", "--state", self.state, "--root", self.root], now=monday)
        self.assertEqual(self.files(), [])
        S.main(["--weekly", "--state", self.state, "--root", self.root], now=SUNDAY)
        p = os.path.join(self.root, "reports", "scorecard", "2026-W46.json")
        first = open(p).read()
        S.main(["--weekly", "--state", self.state, "--root", self.root], now=SUNDAY + datetime.timedelta(hours=8))
        self.assertEqual(open(p).read(), first)

    def test_reports_folder_is_ignored_by_git(self):
        ign = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().split()
        self.assertIn("reports/", ign)


class Workflow(unittest.TestCase):
    def steps(self):
        wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8"))
        return next(iter(wf["jobs"].values()))["steps"]

    def test_sweep_calls_it_after_commit_before_private_save(self):
        st = self.steps()
        sc = [n for n, s in enumerate(st) if "scripts/scorecard.py" in s.get("run", "")]
        self.assertEqual(len(sc), 1)
        s = st[sc[0]]
        com = next(n for n, x in enumerate(st) if str(x.get("name", "")).startswith("Commit"))
        save = next(n for n, x in enumerate(st) if "private_state.sh save" in x.get("run", ""))
        self.assertTrue(com < sc[0] < save)
        self.assertIn("refs/heads/main", s.get("if", ""))
        self.assertIs(s.get("continue-on-error"), True)
        self.assertLessEqual(int(s.get("timeout-minutes", 999)), 5)
        self.assertIn("--weekly", s["run"])
        self.assertIn("private-state/site-run-state", s["run"])
        self.assertNotIn("HELPMAP_STATE_KEY", json.dumps(s))


if __name__ == "__main__":
    unittest.main()
