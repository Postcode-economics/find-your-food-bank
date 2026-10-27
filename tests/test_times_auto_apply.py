"""Strict opening-times auto-apply (Dean 27 Oct 2026). Each safeguard must block on its own; one positive case applies."""
import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import times_finder as F
import times_revert as R
ON, OFF = {"times_auto_apply": True}, {"times_auto_apply": False}
ITEM = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
GOOD = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
        "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27"}
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
        log = self.run_(); self.assertEqual(log["applied"], ["fb1"])
        cur = json.load(open("overrides/opening_times.json")); self.assertEqual(cur["fb1"]["structured"], GOOD["structured"])
        rec = json.load(open(F.AUTO_LOG))[0]
        self.assertEqual((rec["old"], rec["new"]["structured"], rec["source_url"], rec["first_run_at"], rec["second_run_at"]),
                         (None, GOOD["structured"], GOOD["source_url"], "2026-10-26T19:05:00+00:00", "2026-10-27T03:05:00+00:00"))
        R.revert("fb1", root=self.d); self.assertNotIn("fb1", json.load(open("overrides/opening_times.json")))
        self.assertTrue(json.load(open(F.AUTO_LOG))[0]["reverted"])
    def test_off_holds_everything(self):
        self.held(self.run_(rules=OFF), "auto-apply is off"); self.assertFalse(os.path.exists(F.AUTO_LOG))
    def test_missing_key_is_off(self): self.held(self.run_(rules={}), "auto-apply is off")
    def test_postcode_not_matched(self): self.held(self.run_(ot=dict(GOOD, pc_seen=[])), "postcode not matched")
    def test_only_one_run(self): self.held(self.run_(seen={}), "2 separate runs")
    def test_two_runs_differ(self):
        s = {"fb1": dict(SEEN1["fb1"], sig=json.dumps({"thu": [["10:00", "12:00"]]}))}; self.held(self.run_(seen=s), "2 separate runs")
    def test_two_runs_other_url(self):
        s = {"fb1": dict(SEEN1["fb1"], source_url="https://testfb.org.uk/other")}; self.held(self.run_(seen=s), "2 separate runs")
    def test_same_run_twice_is_not_two_runs(self):
        s = {"fb1": dict(SEEN1["fb1"], run_at="2026-10-27T03:05:00+00:00")}; self.held(self.run_(seen=s), "2 separate runs")
    def test_not_own_site(self):
        ot = dict(GOOD, source_url="https://directory.example.com/testfb"); s = {"fb1": dict(SEEN1["fb1"], source_url=ot["source_url"])}
        self.held(self.run_(ot=ot, seen=s), "own site")
    def test_conflict_with_other_source(self):
        cur = {"fb1": dict(GOOD, structured={"fri": [["09:00", "11:00"]]}, source_url="https://www.givefood.org.uk/x")}
        self.held(self.run_(cur=cur), "conflicts with")
    def test_known_to_closed(self):
        cur = {"fb1": dict(GOOD)}; ot = dict(GOOD, structured={"wed": []}); s = {"fb1": dict(SEEN1["fb1"], sig=json.dumps(ot["structured"], sort_keys=True))}
        r = self.held(self.run_(ot=ot, cur=cur, seen=s), "closed/empty")
    def test_seen_state_written_for_next_run(self):
        self.run_(seen={}); self.assertEqual(json.load(open(F.SEEN))["fb1"]["run_at"], "2026-10-27T03:05:00+00:00")
    def test_repo_rule_present(self):
        import auto_rules; self.assertIs(auto_rules.load().get("times_auto_apply"), True)
if __name__ == "__main__": unittest.main()
