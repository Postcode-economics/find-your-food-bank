"""Dean's rule: food bank opening-times auto-update is the intended feature. A clean change (identical times on 2
separate runs, the food bank's own site, no conflicting source, never known times -> closed/empty) must still go on
the map by itself, end to end: times_finder.run() reads a fake own site through the real reader, the repo's own
overrides/auto_apply_rules.json decides, and overrides/opening_times.json + the undo log are written. The safeguards
(undone map, day_same_line, text-only conflict, run_at, finder-only revert) must not block it."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import times_finder as F, times_revert as R

SITE = "https://testfb.org.uk/"
NEW = {"https://testfb.org.uk/": '<html><body><a href="/opening-times">Opening times</a><p>Welcome to Test Foodbank</p></body></html>',
       "https://testfb.org.uk/opening-times": "<html><body><h1>Opening times</h1><p>Test Foodbank, Church Hall, AB1 2CD</p>"
                                              "<p>Wednesday 10am - 12pm</p></body></html>"}
OLD_TABLE = {"wed": [["09:00", "11:00"]]}
ITEMS = [{"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": SITE, "type": "foodbank"},
         {"id": "fb2", "name": "Other Foodbank", "postcode": "ZZ9 9ZZ", "website": "", "type": "foodbank"}]
RUNS = ("2026-10-27T03:05:00+00:00", "2026-10-27T11:05:00+00:00", "2026-10-27T19:05:00+00:00")


class CleanChangeAutoApplies(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd(); self.d = tempfile.mkdtemp(); os.chdir(self.d)
        for x in ("logs", "reports", "overrides"): os.makedirs(x)
        self.orig = (F.polite, F.known)
        F.polite = lambda u, tries=3: (200, u, NEW[u]) if u in NEW else (404, u, "")
        F.known = lambda: {"pages": {}, "skip": {}}
    def tearDown(self):
        F.polite, F.known = self.orig; os.chdir(self.old); shutil.rmtree(self.d, True)
    def cur(self): return json.load(open("overrides/opening_times.json"))
    def run_(self, now): return F.run([dict(i) for i in ITEMS], threads=1, now=now)

    def test_repo_rules_have_auto_apply_on(self):
        self.assertTrue(F.times_auto_on())

    def test_clean_change_applies_on_the_second_identical_run(self):
        # Previous own-site override with an older table; a refresh-path undo for the same id and a finder undo for
        # another id must not block this finder change.
        json.dump({"fb1": {"status": "TIMES_FOUND", "structured": OLD_TABLE, "raw": "Wednesday 9am - 11am",
                           "source_url": SITE + "opening-times", "reader": "times_finder"}}, open("overrides/opening_times.json", "w"))
        json.dump({"fb:fb1": json.dumps({"wed": [["10:00", "12:00"]]}, sort_keys=True),
                   "finder:fb9": json.dumps({"wed": [["10:00", "12:00"]]}, sort_keys=True)}, open(F.UNDONE, "w"))
        first = self.run_(RUNS[0])
        self.assertEqual(first["applied"], [])
        self.assertEqual([r["why"] for r in first["review"]], [["times not read identically on 2 separate runs yet"]])
        self.assertEqual(self.cur()["fb1"]["structured"], OLD_TABLE)

        second = self.run_(RUNS[1])
        self.assertEqual((second["applied"], second["review"]), (["fb1"], []))
        cur = self.cur()["fb1"]
        self.assertEqual((cur["structured"], cur["source_url"], cur["status"]), ({"wed": [["10:00", "12:00"]]}, SITE + "opening-times", "TIMES_FOUND"))
        self.assertNotIn("_run_at", cur)
        log = json.load(open(F.AUTO_LOG))
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["id"], log[0]["old"]["structured"], log[0]["first_run_at"], log[0]["second_run_at"]), ("fb1", OLD_TABLE, RUNS[0], RUNS[1]))
        self.assertNotIn("path", log[0])
        self.assertIn("AUTO-APPLIED `fb1`", open("reports/pending_dean.md").read())

        third = self.run_(RUNS[2])   # still the same on the site: stays applied, logged once
        self.assertEqual(third["applied"], ["fb1"]); self.assertEqual(len(json.load(open(F.AUTO_LOG))), 1)

    def test_new_food_bank_times_with_nothing_stored_apply(self):
        self.run_(RUNS[0]); self.assertEqual(self.run_(RUNS[1])["applied"], ["fb1"])
        self.assertEqual(self.cur()["fb1"]["structured"], {"wed": [["10:00", "12:00"]]})
        self.assertIsNone(json.load(open(F.AUTO_LOG))[0]["old"])

    def test_after_dean_undoes_it_it_stays_undone_and_a_later_clean_change_still_applies(self):
        self.run_(RUNS[0]); self.assertEqual(self.run_(RUNS[1])["applied"], ["fb1"])
        R.revert("fb1", root=self.d)
        self.assertNotIn("fb1", self.cur())
        held = self.run_(RUNS[2])
        self.assertEqual(held["applied"], []); self.assertNotIn("fb1", self.cur())
        self.assertIn("undone by Dean", "; ".join(held["review"][0]["why"]))
        # The food bank then publishes new times: a different clean change, which auto-applies again.
        NEW_PAGE = dict(NEW); NEW_PAGE[SITE + "opening-times"] = NEW[SITE + "opening-times"].replace("Wednesday 10am - 12pm", "Thursday 1pm - 3pm")
        F.polite = lambda u, tries=3: (200, u, NEW_PAGE[u]) if u in NEW_PAGE else (404, u, "")
        F.run([dict(i) for i in ITEMS], threads=1, now="2026-10-28T03:05:00+00:00")
        again = F.run([dict(i) for i in ITEMS], threads=1, now="2026-10-28T11:05:00+00:00")
        self.assertEqual(again["applied"], ["fb1"])
        self.assertEqual(self.cur()["fb1"]["structured"], {"thu": [["13:00", "15:00"]]})


if __name__ == "__main__": unittest.main()
