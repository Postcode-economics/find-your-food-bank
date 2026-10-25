"""A once-a-year reminder to re-read source terms. It adds no URLs and does not nag on the day it was written."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, source_terms
from test_learning_guards import assert_schedule_and_guards

class Terms(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        os.makedirs(os.path.join(self.d, "reports"))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        for rel in (".github/workflows/sweep-daily.yml", ".github/workflows/refresh.yml"):
            text = open(os.path.join(R, rel), encoding="utf-8").read()
            self.assertNotIn("source_terms", text)
    def test_the_written_day_and_the_year_before_are_quiet(self):
        path = os.path.join(self.d, "reports", "source_terms.json")
        for day in ("2026-10-25", "2026-10-26", "2027-10-24"):
            self.assertIsNone(source_terms.consider(datetime.date.fromisoformat(day), path))
        self.assertFalse(os.path.exists(path))
    def test_the_anniversary_reminds_once_and_adds_no_urls(self):
        path = os.path.join(self.d, "reports", "source_terms.json")
        row = source_terms.consider(datetime.date(2027, 10, 25), path)
        self.assertIn("re-read the terms", row["line"])
        self.assertEqual(row["urls"], [])
        self.assertNotIn("http", row["line"])
        saved = json.load(open(path))
        self.assertEqual(saved, {"last": "2027-10-25"})
        self.assertNotIn("http", json.dumps(saved))
        self.assertIsNone(source_terms.consider(datetime.date(2027, 10, 26), path))
        self.assertEqual(json.load(open(path))["last"], "2027-10-25")
        again = source_terms.consider(datetime.date(2028, 10, 25), path)
        self.assertEqual(again["last"], "2028-10-25")
        self.assertEqual(again["urls"], [])
    def test_the_morning_note_stays_quiet_today(self):
        open(os.path.join(self.d, "data.full.js"), "w").write('window.FB_DATA={"items":[]};')
        json.dump({"sites": {}}, open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 25))
        self.assertIn("no source-terms reminder", o["terms_note"])
        self.assertIn("No URLs were added", o["terms_note"])
        self.assertFalse(os.path.exists(os.path.join(self.d, "reports", "source_terms.json")))
        due = LS.build(datetime.date(2027, 10, 25))
        self.assertIn("re-read the terms", due["terms_note"])
        self.assertNotIn("http", due["terms_note"])

if __name__ == "__main__":
    unittest.main()
