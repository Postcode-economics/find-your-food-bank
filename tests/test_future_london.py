"""The morning note names London time. The scheduled clock does not move."""
import os, sys, datetime, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import digest
from test_learning_guards import assert_schedule_and_guards

class London(unittest.TestCase):
    def test_schedule_unchanged(self):
        assert_schedule_and_guards()
        text = open(os.path.join(R, "scripts", "digest.py"), encoding="utf-8").read()
        self.assertIn("Europe/London", text)
        for rel, cron in {
            ".github/workflows/refresh.yml": "29 4,12,20 * * *",
            ".github/workflows/sweep-daily.yml": "5 3,11,19 * * *",
            ".github/workflows/swep-daily.yml": "0 5 * * *",
            ".github/workflows/fb-page-check.yml": "40 6 * * *",
            ".github/workflows/watchdog.yml": "17 * * * *",
            ".github/workflows/deploy-check.yml": "15 6 * * *",
        }.items():
            self.assertIn(cron, open(os.path.join(R, rel), encoding="utf-8").read())
    def test_summer_and_winter(self):
        utc = datetime.timezone.utc
        self.assertEqual(digest.london_label(datetime.datetime(2026, 6, 15, 3, 30, tzinfo=utc)), "Monday 15 June 2026, 04:30 BST")
        self.assertEqual(digest.london_label(datetime.datetime(2026, 1, 15, 4, 30, tzinfo=utc)), "Thursday 15 January 2026, 04:30 GMT")

if __name__ == "__main__":
    unittest.main()
