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
        self.assertIsNone(c["brake"]["trip_on_file_this_week"])  # no anomaly key: not a made-up 0

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
    def setUp(self):
        super().setUp()
        self._runs = mock.patch.object(S, "runs", return_value={l: None for l in S.LAYERS})
        self._runs.start()

    def tearDown(self):
        self._runs.stop()
        super().tearDown()

    def files(self):
        out = []
        for d, _, fs in os.walk(self.root):
            out += [os.path.relpath(os.path.join(d, f), self.root) for f in fs]
        return sorted(out)

    def test_writes_only_reports_scorecard(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN": "dummy-token-must-not-be-used"}):
            with mock.patch.object(S.urllib.request, "urlopen", side_effect=AssertionError("live GitHub API call")) as u:
                self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
                u.assert_not_called()
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


class ReviewFixes(Fixture):
    """R1-R4 / S1-S2 from the review of c05b1cf5, and C1-C3 from the review of 9f2a2df2."""

    def test_r1_missing_held_keys_are_null_not_zero(self):
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14",
            "layers": {"foodbanks": {"held": 3, "applied": 1, "stale_cleared": 0}},
        })
        ld = self.card()["layers"]["foodbanks"]["latest_day"]
        self.assertEqual(ld["held"], 3)
        self.assertIsNone(ld["coverage_gate_blocks"])
        self.assertIsNone(ld["errors"])
        self.assertIsNone(ld["rejected_listed"])
        md = S.render(self.card())
        self.assertIn("coverage-gate blocks no data yet", md)
        self.assertNotRegex(md, r"coverage-gate blocks 0")

    def test_r1_missing_discovery_and_brake_keys_are_null_not_zero(self):
        put(self.state, "foodbanks/logs/discovery_today_foodbanks.json", {"day": "2026-11-14"})
        put(self.state, "foodbanks/reports/learning_state.json", {})
        c = self.card()
        d = c["layers"]["foodbanks"]["discovery"]
        self.assertEqual(d["day"], "2026-11-14")
        self.assertIsNone(d["queued"])
        self.assertIsNone(d["runs_that_day"])
        put(self.state, "foodbanks/logs/discovery_today_foodbanks.json", {"day": "2026-11-14", "queued": ["not", "a", "dict"]})
        self.assertIsNone(self.card()["layers"]["foodbanks"]["discovery"]["queued"])
        b = c["brake"]
        self.assertIsNone(b["runs_counted_this_week"])
        self.assertIsNone(b["max_changes_in_a_run"])
        self.assertIsNone(b["trip_on_file_this_week"])
        put(self.state, "foodbanks/reports/learning_state.json",
            {"change_counts": [{"day": "2026-11-10"}]})  # record exists, but no numeric changes
        b2 = self.card()["brake"]
        self.assertEqual(b2["runs_counted_this_week"], 1)
        self.assertIsNone(b2["max_changes_in_a_run"])

    def test_r2_partial_held_total_is_labelled_not_shown_as_all_layers(self):
        c = self.card()
        self.assertEqual(c["layers"]["foodbanks"]["latest_day"]["held"], 3)
        self.assertIsNone(c["layers"]["shelters"]["latest_day"])
        self.assertIsNone(c["layers"]["warmspaces"]["latest_day"])
        md = S.render(c)
        line = [ln for ln in md.splitlines() if ln.startswith("2. Opening-time changes held")][0]
        self.assertIn("partial: food banks only", line)
        self.assertNotIn("held on the latest run day (food banks, shelters, warm spaces): 3;", line)

    def test_r3_brake_trip_is_yes_no_not_a_count_capped_at_one(self):
        put(self.state, "foodbanks/reports/learning_state.json", {
            "anomaly": {"stop": True, "day": "2026-11-12", "reason": "r"},
        })
        c = self.card()
        self.assertIs(c["brake"]["trip_on_file_this_week"], True)
        self.assertNotIn("trips_this_week", c["brake"])
        md = S.render(c)
        self.assertIn("Brake trip on file this week: yes", md)
        self.assertIn("trip on file this week: yes", md)
        self.assertNotIn("Brake trips this week", md)
        put(self.state, "foodbanks/reports/learning_state.json", {
            "anomaly": {"stop": True, "day": "2026-11-03", "reason": "old"},
        })
        self.assertIs(self.card()["brake"]["trip_on_file_this_week"], False)
        self.assertIn("Brake trip on file this week: no", S.render(self.card()))

    def test_r4_main_does_not_call_github_when_token_is_set(self):
        # Same call path as test_writes_only_reports_scorecard, with GH_TOKEN set as the sweep's
        # "Full test suite" step does. S.runs is stubbed so no real API call can go out.
        with mock.patch.object(S, "runs", return_value={l: None for l in S.LAYERS}):
            with mock.patch.dict(os.environ, {"GH_TOKEN": "dummy-token-must-not-be-used"}):
                with mock.patch.object(S.urllib.request, "urlopen", side_effect=AssertionError("live GitHub API call")) as u:
                    self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"], now=SUNDAY), 0)
                    u.assert_not_called()

    def test_s1_one_bad_field_does_not_skip_the_card(self):
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "would_block": [],
            "layers": {"foodbanks": {"held": 3, "applied": 1, "errors": [], "rejected": ["not-a-dict", "also-a-string"]}},
        })
        put(self.state, "foodbanks/reports/learning_state.json",
            {"change_counts": [{"day": "2026-11-10", "changes": "x"}]})
        put(self.state, "shelters/reports/shadow/shelters/2026-11-13.json",
            {"runs": [{"candidates": "abc", "rules": {}}]})
        put(self.state, "shelters/reports/shadow/trial.json", {"start": "2026-11-12"})
        prev_str = {"week": "2026-W45", "layers": {"foodbanks": {"latest_day": "not-a-dict", "pending": {"ids": ["a"]}}}}
        c = S.build(self.state, "2026-W46", prev=prev_str, now=SUNDAY, gh={l: None for l in S.LAYERS})
        self.assertEqual(c["layers"]["foodbanks"]["latest_day"]["held"], 3)
        self.assertEqual(c["layers"]["foodbanks"]["latest_day"]["rejected_listed"], 2)
        self.assertIsNone(c["brake"]["max_changes_in_a_run"])
        self.assertEqual(c["brake"]["runs_counted_this_week"], 1)
        self.assertIsNone(c["layers"]["foodbanks"]["held_at_last_card_auto_applied_since"])
        # previous card is a list: still writes
        c2 = S.build(self.state, "2026-W46", prev=["not", "a", "card"], now=SUNDAY, gh={l: None for l in S.LAYERS})
        self.assertEqual(c2["week"], "2026-W46")
        self.assertIsNone(c2["week_on_week"])
        # main still writes a card (does not skip)
        self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"],
                                now=SUNDAY, gh={l: None for l in S.LAYERS}), 0)
        self.assertTrue(os.path.exists(os.path.join(self.root, "reports", "scorecard", "2026-W46.md")))

    def test_s2_reasons_string_is_one_reason_not_letters(self):
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "would_block": [],
            "layers": {"foodbanks": {"held": 1, "applied": 0, "errors": [],
                                     "rejected": [{"id": "x", "reasons": "why"}]}},
        })
        put(self.state, "foodbanks/logs/discovery_today_foodbanks.json", {
            "day": "2026-11-14", "queued": {"q1": {"reasons": "hold"}}, "runs": [],
        })
        c = self.card()
        self.assertEqual(c["layers"]["foodbanks"]["latest_day"]["hold_reasons"], {"why": 1})
        self.assertNotEqual(c["layers"]["foodbanks"]["latest_day"]["hold_reasons"], {"h": 1, "w": 1, "y": 1})
        self.assertEqual(c["layers"]["foodbanks"]["discovery"]["queue_reasons"], {"hold": 1})


    def test_c1_non_numeric_headline_does_not_skip_the_card(self):
        # P24: last week's held is the string "5". Compare used to TypeError and skip the card.
        prev = {"week": "2026-W45", "layers": {"foodbanks": {"latest_day": {"held": "5"}}}}
        c = S.build(self.state, "2026-W46", prev=prev, now=SUNDAY, gh={l: None for l in S.LAYERS})
        self.assertEqual(c["week"], "2026-W46")
        self.assertEqual(c["week_on_week"]["previous_week"], "2026-W45")
        self.assertIsNone(c["week_on_week"]["change"]["foodbanks"]["held_latest_day"])
        self.assertIsNotNone(S.render(c))
        # P33: this week's held is the string "53" and a previous numeric card exists.
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "layers": {"foodbanks": {"held": "53", "applied": 1, "stale_cleared": 0}},
        })
        prev_num = {"week": "2026-W45", "layers": {"foodbanks": {"latest_day": {"held": 5}}}}
        c2 = S.build(self.state, "2026-W46", prev=prev_num, now=SUNDAY, gh={l: None for l in S.LAYERS})
        self.assertIsNone(c2["layers"]["foodbanks"]["latest_day"]["held"])
        self.assertIsNone(c2["week_on_week"]["change"]["foodbanks"]["held_latest_day"])
        # main used to print "scorecard: skipped (TypeError)" and write nothing
        put(self.root, "reports/scorecard/2026-W45.json", prev)
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            self.assertEqual(S.main(["--state", self.state, "--root", self.root, "--week", "2026-W46"],
                                    now=SUNDAY, gh={l: None for l in S.LAYERS}), 0)
        self.assertNotIn("skipped", buf.getvalue())
        self.assertIn("wrote", buf.getvalue())
        self.assertTrue(os.path.exists(os.path.join(self.root, "reports", "scorecard", "2026-W46.md")))
        md = open(os.path.join(self.root, "reports", "scorecard", "2026-W46.md"), encoding="utf-8").read()
        self.assertNotIn("could not be built", md)

    def test_c2_boolean_and_string_counts_are_not_shown_as_numbers(self):
        # P29: held "53" must be null, not the string, and markdown must still build
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "layers": {"foodbanks": {"held": "53", "applied": True, "stale_cleared": "0"}},
        })
        c = self.card()
        ld = c["layers"]["foodbanks"]["latest_day"]
        self.assertIsNone(ld["held"])
        self.assertIsNone(ld["applied_that_day"])
        self.assertIsNone(ld["stale_cleared"])
        md = S.render(c)
        self.assertNotIn("could not be built", md)
        line = [ln for ln in md.splitlines() if ln.startswith("2. Opening-time changes held")][0]
        self.assertIn("no data yet", line)
        self.assertNotRegex(line, r": 53")
        # P30: held true must be null, never the invented count 1
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "layers": {"foodbanks": {"held": True, "applied": 1, "stale_cleared": 0}},
        })
        c2 = self.card()
        self.assertIsNone(c2["layers"]["foodbanks"]["latest_day"]["held"])
        self.assertIs(c2["layers"]["foodbanks"]["latest_day"]["held"] is True, False)
        line2 = [ln for ln in S.render(c2).splitlines() if ln.startswith("2. Opening-time changes held")][0]
        self.assertIn("no data yet", line2)
        self.assertNotRegex(line2, r": 1\b")
        # P34: last week's held true must not invent a week-on-week change of +6 (7 - 1)
        prev = {"week": "2026-W45", "layers": {"foodbanks": {"latest_day": {"held": True}}}}
        put(self.state, "foodbanks/reports/intelligent_mode.json", {
            "run": "2026-11-14", "layers": {"foodbanks": {"held": 7, "applied": 1, "stale_cleared": 0}},
        })
        c3 = S.build(self.state, "2026-W46", prev=prev, now=SUNDAY, gh={l: None for l in S.LAYERS})
        self.assertEqual(c3["layers"]["foodbanks"]["latest_day"]["held"], 7)
        self.assertIsNone(c3["week_on_week"]["change"]["foodbanks"]["held_latest_day"])

    def test_c3_brake_stop_without_a_readable_day_is_no_data_yet(self):
        # P35: stop is set but there is no day, so the week is unknown — not a "no"
        put(self.state, "foodbanks/reports/learning_state.json", {"anomaly": {"stop": True}, "change_counts": []})
        c = self.card()
        self.assertIsNone(c["brake"]["trip_on_file_this_week"])
        md = S.render(c)
        self.assertIn("Brake trip on file this week: no data yet", md)
        self.assertNotIn("Brake trip on file this week: no\n", md + "\n")
        # unreadable day is the same
        put(self.state, "foodbanks/reports/learning_state.json",
            {"anomaly": {"stop": True, "day": "not-a-day"}, "change_counts": []})
        self.assertIsNone(self.card()["brake"]["trip_on_file_this_week"])
        self.assertIn("Brake trip on file this week: no data yet", S.render(self.card()))
        # a readable day last week is still an honest "no"
        put(self.state, "foodbanks/reports/learning_state.json",
            {"anomaly": {"stop": True, "day": "2026-11-02"}, "change_counts": []})
        self.assertIs(self.card()["brake"]["trip_on_file_this_week"], False)
        self.assertIn("Brake trip on file this week: no", S.render(self.card()))


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
