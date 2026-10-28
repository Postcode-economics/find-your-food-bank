"""Gaps in the strict finder auto-apply (times_finder.decide / strict_checks / times_revert): sticky undo, finder-only
bare-id revert, text-only stored times as a conflict, a seen row with no run_at, and the day_same_line rule."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import times_finder as F, times_revert as R

ON = {"times_auto_apply": True}
ITEM = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
GOOD = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
        "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27"}
SIG = json.dumps(GOOD["structured"], sort_keys=True)
RUNS = ("2026-10-26T19:05:00+00:00", "2026-10-27T03:05:00+00:00", "2026-10-27T11:05:00+00:00", "2026-10-27T19:05:00+00:00")
KS = {"pages": {}, "skip": {}}


class Gaps(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd(); self.d = tempfile.mkdtemp(); os.chdir(self.d)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        json.dump({}, open("overrides/opening_times.json", "w"))
        self.ks = F.known; F.known = lambda: KS
    def tearDown(self):
        os.chdir(self.old); F.known = self.ks; shutil.rmtree(self.d, True)
    def decide(self, now, ot=GOOD, item=ITEM):
        log = {"found": {"fb1": dict(ot)}}; F.decide(log, [dict(item)], False, rules=ON, now=now); return log
    def cur(self): return json.load(open("overrides/opening_times.json"))
    def seen1(self, **kw): return {"fb1": dict({"sig": SIG, "source_url": GOOD["source_url"], "run_at": RUNS[0]}, **kw)}

    def test_undo_is_sticky_the_same_reading_is_not_reapplied(self):
        """Phone and refresh paths block an undone change; the finder path must too."""
        self.decide(RUNS[0]); self.assertEqual(self.decide(RUNS[1])["applied"], ["fb1"])
        R.revert("fb1", root=self.d)
        self.assertEqual(json.load(open(F.UNDONE)), {"finder:fb1": SIG})
        for now in RUNS[2:]:
            log = self.decide(now)
            self.assertEqual(log["applied"], [])
            self.assertTrue(any("undone" in w for w in log["review"][0]["why"]), log["review"])
            self.assertNotIn("fb1", self.cur())

    def test_undo_blocks_only_that_table(self):
        """Dean undid one table. Different times later on the own site are a new change and still auto-apply."""
        json.dump({"finder:fb1": json.dumps({"wed": [["09:00", "11:00"]]}, sort_keys=True), "fb:fb1": SIG}, open(F.UNDONE, "w"))
        self.decide(RUNS[0]); self.assertEqual(self.decide(RUNS[1])["applied"], ["fb1"])
        self.assertEqual(self.cur()["fb1"]["structured"], GOOD["structured"])

    def test_strict_checks_reads_the_undone_map(self):
        why = F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, {}, self.seen1(), 1, KS, {"finder:fb1": SIG})
        self.assertEqual(len(why), 1, why); self.assertIn("undone by Dean", why[0])
        self.assertEqual(F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, {}, self.seen1(), 1, KS, {"fb:fb1": SIG}), [])

    def test_revert_restores_the_previous_override(self):
        old = dict(GOOD, structured={"wed": [["09:00", "11:00"]]}, raw="Wednesday 9-11")
        json.dump({"fb1": old}, open("overrides/opening_times.json", "w"))
        json.dump(self.seen1(), open(F.SEEN, "w"))
        self.assertEqual(self.decide(RUNS[1])["applied"], ["fb1"])   # same source, new table: an update, not a conflict
        self.assertEqual(self.cur()["fb1"]["structured"], GOOD["structured"])
        R.revert("fb1", root=self.d)
        self.assertEqual(self.cur()["fb1"], old)

    def test_revert_with_nothing_logged_exits(self):
        json.dump([], open(F.AUTO_LOG, "w"))
        with self.assertRaises(SystemExit): R.revert("fb1", root=self.d)
        self.assertFalse(os.path.exists(F.UNDONE))

    def test_bare_id_revert_ignores_refresh_path_entries(self):
        """'times_revert.py fb1' is the finder undo. A refresh-path entry for the same id (undo key 'fb:fb1') must not
        be restored into overrides/opening_times.json."""
        rec = {"id": "fb1", "kind": "fb", "path": "cross_check", "old": {"structured": {"tue": [["09:00", "10:00"]]}},
               "new": dict(GOOD), "new_structured": GOOD["structured"], "source_url": GOOD["source_url"]}
        json.dump([rec], open(F.AUTO_LOG, "w"))
        with self.assertRaises(SystemExit): R.revert("fb1", root=self.d)
        self.assertEqual(self.cur(), {})
        self.assertFalse(json.load(open(F.AUTO_LOG))[0].get("reverted"))

    def test_bare_id_revert_picks_the_finder_entry_past_a_newer_refresh_entry(self):
        fin = {"id": "fb1", "old": None, "new": dict(GOOD), "source_url": GOOD["source_url"]}
        xc = {"id": "fb1", "kind": "fb", "path": "cross_check", "old": {"structured": {"tue": [["09:00", "10:00"]]}},
              "new": dict(GOOD), "new_structured": GOOD["structured"], "source_url": GOOD["source_url"]}
        json.dump([fin, xc], open(F.AUTO_LOG, "w")); json.dump({"fb1": dict(GOOD)}, open("overrides/opening_times.json", "w"))
        R.revert("fb1", root=self.d)
        self.assertEqual(self.cur(), {})
        log = json.load(open(F.AUTO_LOG)); self.assertTrue(log[0]["reverted"]); self.assertFalse(log[1].get("reverted"))

    def test_text_only_times_from_another_source_conflict(self):
        """Known times kept as text (no table) from another source are still known times from another source."""
        cur = {"fb1": {"status": "TIMES_FOUND", "raw": "Tuesdays 9-11, call first", "source_url": "https://www.givefood.org.uk/x"}}
        why = F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, cur, self.seen1(), 1, KS)
        self.assertTrue(any("conflicts with" in w for w in why), why)
        cur = {"fb1": {"status": "TIMES_TEXT_ONLY", "structured": None, "raw": "Tuesdays 9-11", "source_url": "https://www.givefood.org.uk/x"}}
        self.assertTrue(any("conflicts with" in w for w in F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, cur, self.seen1(), 1, KS)))

    def test_text_only_times_from_the_same_source_are_not_a_conflict(self):
        cur = {"fb1": {"status": "TIMES_TEXT_ONLY", "structured": None, "raw": "Wednesdays, mornings", "source_url": GOOD["source_url"]}}
        self.assertEqual(F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, cur, self.seen1(), 1, KS), [])

    def test_same_times_from_another_source_is_not_a_conflict(self):
        cur = {"fb1": dict(GOOD, source_url="https://www.givefood.org.uk/x")}
        self.assertEqual(F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, cur, self.seen1(), 1, KS), [])

    def test_known_to_explicit_closed_names_the_closed_rule(self):
        """one_block also refuses a CLOSED reading; the closed/empty rule must fire on its own, not only by accident."""
        seen = self.seen1(sig=None)
        closed = dict(GOOD, status="CLOSED", structured=None, raw="Closed", _run_at=RUNS[1])
        why = F.strict_checks("fb1", closed, ITEM, {"fb1": dict(GOOD)}, seen, 1, KS)
        self.assertTrue(any("closed/empty" in w for w in why), why)
        why = F.strict_checks("fb1", closed, dict(ITEM, opening_times=dict(GOOD)), {}, seen, 1, KS)   # known times on the listing, not an override
        self.assertTrue(any("closed/empty" in w for w in why), why)

    def test_seen_row_without_run_at_is_not_a_second_run(self):
        seen = {"fb1": {"sig": SIG, "source_url": GOOD["source_url"]}}
        why = F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, {}, seen, 1, KS)
        self.assertEqual(len(why), 1, why); self.assertIn("2 separate runs", why[0])
        for blank in ("", None):
            why = F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, {}, self.seen1(run_at=blank), 1, KS)
            self.assertTrue(any("2 separate runs" in w for w in why), why)

    def test_day_not_on_the_same_line_as_its_times_is_held(self):
        """auto_apply_rules.json: the day must be written on the same line as its times (discover.day_same_line)."""
        split = dict(GOOD, raw="Open Wednesday. Times: 10am - 12pm")
        why = F.strict_checks("fb1", dict(split, _run_at=RUNS[1]), ITEM, {}, self.seen1(), 1, KS)
        self.assertEqual(len(why), 1, why); self.assertIn("same line", why[0])
        other_day = dict(GOOD, raw="Thursday 10am - 12pm")
        self.assertTrue(any("same line" in w for w in F.strict_checks("fb1", dict(other_day, _run_at=RUNS[1]), ITEM, {}, self.seen1(), 1, KS)))
        self.assertEqual(F.strict_checks("fb1", dict(GOOD, _run_at=RUNS[1]), ITEM, {}, self.seen1(), 1, KS), [])

    def test_day_same_line_holds_through_decide(self):
        split = dict(GOOD, raw="Open Wednesday. Times: 10am - 12pm")
        self.decide(RUNS[0], ot=split); log = self.decide(RUNS[1], ot=split)
        self.assertEqual(log["applied"], []); self.assertIn("same line", "; ".join(log["review"][0]["why"]))
        self.assertNotIn("fb1", self.cur())

    def test_a_missed_run_resets_the_two_run_count(self):
        self.decide(RUNS[0])
        F.decide({"found": {}}, [dict(ITEM)], False, rules=ON, now=RUNS[1])   # not read on the middle run
        self.assertEqual(self.decide(RUNS[2])["applied"], [])

    def test_applied_row_is_listed_for_dean_with_its_undo(self):
        self.decide(RUNS[0]); self.decide(RUNS[1])
        md = open("reports/pending_dean.md").read()
        self.assertIn("AUTO-APPLIED `fb1`", md); self.assertIn("python scripts/times_revert.py fb1", md)


if __name__ == "__main__": unittest.main()
