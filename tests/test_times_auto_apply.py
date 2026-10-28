"""Strict opening-times auto-apply (Dean 27 Oct 2026). Each safeguard must block on its own; one positive case applies.

One test per rule Dean set:
  postcode must match; the same times on 2 separate runs; the organisation's own site only;
  no source conflict; never change known times to closed or empty; every change is logged with an undo;
  anything unclear is held for Dean.
"""
import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import times_finder as F
import times_revert as R
ON, OFF = {"times_auto_apply": True}, {"times_auto_apply": False}
ITEM = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
GOOD = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
        "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27", "fb_mention": True}
SEEN1 = {"fb1": {"sig": json.dumps(GOOD["structured"], sort_keys=True), "source_url": GOOD["source_url"], "run_at": "2026-10-26T19:05:00+00:00"}}
class Auto(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd(); self.d = tempfile.mkdtemp(); os.chdir(self.d)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        self.ks = F.known; F.known = lambda: {"pages": {}, "skip": {}}
    def tearDown(self): os.chdir(self.old); F.known = self.ks
    def run_(self, ot=GOOD, item=ITEM, seen=SEEN1, cur=None, rules=ON, extra=None):
        json.dump(seen, open(F.SEEN, "w")); json.dump(cur or {}, open("overrides/opening_times.json", "w"))
        found = {"fb1": dict(ot)}; items = [dict(item)]
        for k, v, i in (extra or []): found[k] = v; items.append(i)
        log = {"found": found}; F.decide(log, items, False, rules=rules, now="2026-10-27T03:05:00+00:00"); return log
    def held(self, log, text):
        self.assertEqual(log["applied"], []); r = [x for x in log["review"] if x["id"] == "fb1"][0]
        self.assertEqual(len(r["why"]), 1, r["why"]); self.assertIn(text, r["why"][0]); return r
    def test_positive_applies_and_logs_and_reverts(self):
        """Every change is logged with an undo."""
        log = self.run_(); self.assertEqual(log["applied"], ["fb1"])
        cur = json.load(open("overrides/opening_times.json")); self.assertEqual(cur["fb1"]["structured"], GOOD["structured"])
        rec = json.load(open(F.AUTO_LOG))[0]
        self.assertEqual((rec["old"], rec["new"]["structured"], rec["source_url"], rec["first_run_at"], rec["second_run_at"]),
                         (None, GOOD["structured"], GOOD["source_url"], "2026-10-26T19:05:00+00:00", "2026-10-27T03:05:00+00:00"))
        self.assertIn("python scripts/times_revert.py fb1", rec["revert"])
        R.revert("fb1", root=self.d); self.assertNotIn("fb1", json.load(open("overrides/opening_times.json")))
        self.assertTrue(json.load(open(F.AUTO_LOG))[0]["reverted"])
    def test_off_holds_everything(self):
        self.held(self.run_(rules=OFF), "auto-apply is off"); self.assertFalse(os.path.exists(F.AUTO_LOG))
    def test_missing_key_is_off(self): self.held(self.run_(rules={}), "auto-apply is off")
    def test_postcode_not_matched(self):
        """The postcode must match."""
        self.held(self.run_(ot=dict(GOOD, pc_seen=[])), "postcode not matched")
    def test_only_one_run(self):
        """The same times must appear on 2 separate runs."""
        self.held(self.run_(seen={}), "2 separate runs")
    def test_two_runs_differ(self):
        s = {"fb1": dict(SEEN1["fb1"], sig=json.dumps({"thu": [["10:00", "12:00"]]}))}; self.held(self.run_(seen=s), "2 separate runs")
    def test_two_runs_other_url(self):
        s = {"fb1": dict(SEEN1["fb1"], source_url="https://testfb.org.uk/other")}; self.held(self.run_(seen=s), "2 separate runs")
    def test_same_run_twice_is_not_two_runs(self):
        s = {"fb1": dict(SEEN1["fb1"], run_at="2026-10-27T03:05:00+00:00")}; self.held(self.run_(seen=s), "2 separate runs")
    def test_not_own_site(self):
        """The organisation's own site only."""
        ot = dict(GOOD, source_url="https://directory.example.com/testfb"); s = {"fb1": dict(SEEN1["fb1"], source_url=ot["source_url"])}
        self.held(self.run_(ot=ot, seen=s), "own site")
    def test_conflict_with_other_source(self):
        """No source conflict."""
        cur = {"fb1": dict(GOOD, structured={"fri": [["09:00", "11:00"]]}, source_url="https://www.givefood.org.uk/x")}
        self.held(self.run_(cur=cur), "conflicts with")
    def test_known_to_closed(self):
        """Never change known times to closed or empty."""
        cur = {"fb1": dict(GOOD)}; ot = dict(GOOD, structured={"wed": []}); s = {"fb1": dict(SEEN1["fb1"], sig=json.dumps(ot["structured"], sort_keys=True))}
        self.held(self.run_(ot=ot, cur=cur, seen=s), "closed/empty")
    def test_unclear_is_held_for_dean(self):
        """Anything unclear is held for Dean. Office-like hours are not one clear client block."""
        office = {d: [["09:00", "17:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}
        ot = dict(GOOD, structured=office, raw="Monday to Friday 9am - 5pm")
        seen = {"fb1": {"sig": json.dumps(office, sort_keys=True), "source_url": GOOD["source_url"], "run_at": "2026-10-26T19:05:00+00:00"}}
        self.held(self.run_(ot=ot, seen=seen), "not one clear")
        self.assertIn("fb1", open("reports/pending_dean.md").read())
        self.assertFalse(os.path.exists(F.AUTO_LOG))
    def test_seen_state_written_for_next_run(self):
        self.run_(seen={}); self.assertEqual(json.load(open(F.SEEN))["fb1"]["run_at"], "2026-10-27T03:05:00+00:00")
    def test_repo_rule_present(self):
        import auto_rules; self.assertIs(auto_rules.load().get("times_auto_apply"), True)
    def test_nothing_read_keeps_stored_listing_and_adds_no_pending_row(self):
        """Dean 27 Oct 2026 12:12 GMT: if times cannot be found or read, the stored listing stays exactly as it is."""
        stored = {"fb1": dict(GOOD)}
        json.dump(stored, open("overrides/opening_times.json", "w"))
        open("reports/pending_dean.md", "w").write(
            "# Pending for Dean\n\n<!-- times review -->\nNothing pending.\n<!-- /times review -->\n\n<!-- closures -->\nkeep me\n<!-- /closures -->\n")
        items = [dict(ITEM, phone="01111 111111", tel="01111 111111", opening_times=dict(GOOD))]
        before = json.loads(json.dumps(items[0]))
        log = {"found": {"fb1": {"status": "NO_TIMES"}}}
        F.decide(log, items, False, rules=ON, now="2026-10-27T03:05:00+00:00")
        self.assertEqual(log["applied"], []); self.assertEqual(log["review"], [])
        self.assertEqual(json.load(open("overrides/opening_times.json"))["fb1"]["structured"], GOOD["structured"])
        self.assertEqual(items[0]["opening_times"], before["opening_times"])
        self.assertEqual((items[0]["phone"], items[0]["tel"]), ("01111 111111", "01111 111111"))
        md = open("reports/pending_dean.md").read()
        self.assertNotIn("Nothing pending", md); self.assertNotIn("fb1", md); self.assertNotIn("times review", md)
        self.assertIn("keep me", md)
        self.assertFalse(os.path.exists(F.AUTO_LOG))
        F.decide({"found": {}}, [dict(ITEM, opening_times=dict(GOOD))], False, rules=ON, now="2026-10-27T04:05:00+00:00")
        md = open("reports/pending_dean.md").read()
        self.assertNotIn("Nothing pending", md); self.assertNotIn("fb1", md)
    def test_phone_mismatch_is_not_an_hours_conflict(self):
        """Dean 27 Oct 2026 12:13 GMT: a stored phone that differs from the site phone is not an hours conflict. The phone stays held."""
        item = dict(ITEM, phone="01111 111111", tel="01111 111111")
        ot = dict(GOOD, raw="Wednesday 10am-12pm. Phone 09999 999999")
        log = self.run_(ot=ot, item=item)
        self.assertEqual(log["applied"], ["fb1"]); self.assertEqual(log["review"], [])
        cur = json.load(open("overrides/opening_times.json"))["fb1"]
        self.assertEqual(cur["structured"], GOOD["structured"])
        self.assertNotIn("phone", cur); self.assertNotIn("tel", cur)
        self.assertEqual((item["phone"], item["tel"]), ("01111 111111", "01111 111111"))
        cur_old = {"fb1": dict(GOOD, structured={"fri": [["09:00", "11:00"]]}, source_url="https://www.givefood.org.uk/x")}
        held = self.held(self.run_(cur=cur_old, item=dict(item, phone="09999 999999")), "conflicts with")
        self.assertNotIn("phone", " ".join(held["why"]).lower())
    def test_all_closed_does_not_replace_known_times(self):
        cur = {"fb1": dict(GOOD)}
        ot = dict(GOOD, all_closed=True, structured={"mon": [["09:00", "17:00"]]}, raw="Closed")
        seen = {"fb1": {"sig": json.dumps(ot["structured"], sort_keys=True), "source_url": GOOD["source_url"], "run_at": "2026-10-26T19:05:00+00:00"}}
        self.held(self.run_(ot=ot, cur=cur, seen=seen), "closed/empty")
        self.assertEqual(json.load(open("overrides/opening_times.json"))["fb1"]["structured"], GOOD["structured"])
        self.assertNotIn("all_closed", json.load(open("overrides/opening_times.json"))["fb1"])
if __name__ == "__main__": unittest.main()
