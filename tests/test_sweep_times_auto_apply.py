"""Dean 28 Oct 2026: food bank opening times update automatically from the daily sweep (the intended feature).
Only address and phone changes need his approval. A clean food bank times change read identically on 2 sweep runs
must still be applied end to end: own-site read (times_finder.generic), the strict gate (strict_checks), the live
auto_apply_rules.json switch, overrides/opening_times.json written, one undo entry and the AUTO-APPLIED row for Dean.
The sweep runs times_finder.py without --apply, so the apply argument must not hold it back."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import times_finder as TF, times_revert

SITE = "https://riverside-foodbank.org.uk/"
PAGE = SITE + "opening-times/"
TEXT = ("Riverside Foodbank\nWhere to find us: Riverside Hall, 1 Mill Lane, AB1 2CD\n"
        "Tuesday 10am - 12pm\nThursday 1pm - 3pm\nPlease bring your voucher.")
ITEM = {"id": "riverside", "type": "foodbank", "name": "Riverside Foodbank", "postcode": "AB1 2CD", "website": SITE,
        "phone": "01234 567890", "address": "Riverside Hall, 1 Mill Lane, AB1 2CD"}
RUNS = ("2026-10-28T03:05:00+00:00", "2026-10-28T11:05:00+00:00")


class SweepAutoAppliesFoodBankTimes(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd(); self.d = tempfile.mkdtemp(); os.chdir(self.d)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        json.dump({}, open("overrides/opening_times.json", "w"))
        self.orig = (TF.site_texts, TF.known)
        TF.site_texts = lambda base, maxpages=10: (200, SITE, [(SITE, "Riverside Foodbank. Welcome."), (PAGE, TEXT)])
        TF.known = lambda: {"pages": {}, "skip": {}}
    def tearDown(self):
        TF.site_texts, TF.known = self.orig; os.chdir(self.old); shutil.rmtree(self.d, True)

    def sweep(self, now):
        found = {k: v[0] for k, v in TF.generic([dict(ITEM)], SITE).items() if v[0]}
        log = {"found": found}
        TF.decide(log, [dict(ITEM)], False, rules=None, now=now)   # the sweep's call: no --apply, the live rules file
        return log

    def test_clean_two_run_change_auto_applies_end_to_end(self):
        self.assertTrue(TF.times_auto_on(), "overrides/auto_apply_rules.json times_auto_apply must stay on for food bank times")
        first = self.sweep(RUNS[0])
        self.assertEqual(first["applied"], [])
        self.assertTrue(any("2 separate runs" in w for r in first["review"] for w in r["why"]), first["review"])
        second = self.sweep(RUNS[1])
        self.assertEqual(second["applied"], ["riverside"], second["review"])
        cur = json.load(open("overrides/opening_times.json"))["riverside"]
        self.assertEqual(cur["structured"], {"tue": [["10:00", "12:00"]], "thu": [["13:00", "15:00"]]})
        self.assertEqual(cur["source_url"], PAGE)
        log, = json.load(open(TF.AUTO_LOG))
        self.assertEqual((log["id"], log["first_run_at"], log["second_run_at"]), ("riverside", RUNS[0], RUNS[1]))
        self.assertEqual(log["revert"], "python scripts/times_revert.py riverside")
        self.assertIn("AUTO-APPLIED `riverside`", open("reports/pending_dean.md").read())

    def test_times_only_phone_and_address_are_not_touched(self):
        self.sweep(RUNS[0]); self.sweep(RUNS[1])
        cur = json.load(open("overrides/opening_times.json"))["riverside"]
        self.assertFalse({"phone", "tel", "address", "postcode"} & set(cur))

    def test_dean_can_still_undo_it(self):
        self.sweep(RUNS[0]); self.sweep(RUNS[1])
        times_revert.revert("riverside", root=self.d)
        self.assertNotIn("riverside", json.load(open("overrides/opening_times.json")))


if __name__ == "__main__":
    unittest.main()
