"""HTTP 429 pauses a host for the rest of the run. The weekly check and the clock stay."""
import os, sys, json, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import rate_ledger, learning
from test_learning_guards import assert_schedule_and_guards

class Rates(unittest.TestCase):
    def setUp(self):
        self.ledger = rate_ledger.Ledger(); rate_ledger.LEDGER = self.ledger
    def tearDown(self):
        rate_ledger.LEDGER = rate_ledger.Ledger()
    def test_schedule_and_floor_unchanged(self):
        assert_schedule_and_guards()
        self.assertEqual(learning.FLOOR_DAYS, 7)
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("paused this run after HTTP 429", fc)
        self.assertIn("29 4,12,20 * * *", open(os.path.join(R, ".github", "workflows", "refresh.yml"), encoding="utf-8").read())
    def test_429_pauses_the_host_and_counts_the_call(self):
        L = self.ledger
        self.assertTrue(L.allow("https://api.postcodes.io/postcodes"))
        L.record("https://api.postcodes.io/postcodes", 200)
        L.record("https://api.postcodes.io/postcodes?q=1", 429)
        self.assertFalse(L.allow("https://api.postcodes.io/postcodes/SW1A1AA"))
        self.assertEqual(L.counts["postcodes.io"], 2)
        self.assertIn("paused for the rest of this run", L.note())
        self.assertNotIn("postcodes.io", L.counts.get("facebook.com", ""))
    def test_groups_the_named_hosts(self):
        self.assertEqual(rate_ledger.host_of("https://api.naturalresources.wales/floodwarnings/v3/all"), "naturalresources.wales")
        self.assertEqual(rate_ledger.host_of("https://www.metoffice.gov.uk/public/data/x"), "metoffice.gov.uk")
        self.assertEqual(rate_ledger.host_of("https://www.facebook.com/food"), "facebook.com")
    def test_save_merges_one_day_and_does_not_invent_calls(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "rate_ledger.json")
        self.ledger.record("https://api.postcodes.io/postcodes", 200)
        rate_ledger.save(p, "2026-10-26")
        self.ledger.counts.clear()
        self.ledger.record("https://www.facebook.com/x", 429)
        rate_ledger.save(p, "2026-10-26")
        saved = json.load(open(p))
        self.assertEqual(saved["counts"], {"facebook.com": 1, "postcodes.io": 1})
        self.assertEqual(saved["paused"], ["facebook.com"])
        self.ledger.counts.clear(); self.ledger.paused.clear()
        self.ledger.record("https://example.test/", 200)
        rate_ledger.save(p, "2026-10-27")
        saved = json.load(open(p))
        self.assertEqual(saved["counts"], {"example.test": 1})
        self.assertEqual(rate_ledger.note_from({}), "no calls recorded - no effect")

if __name__ == "__main__":
    unittest.main()
