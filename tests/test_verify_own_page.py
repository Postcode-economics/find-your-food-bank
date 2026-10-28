import csv
import io
import os
import sys
import tempfile
import unittest

R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import verify_own_page as V

FIX = os.path.join(R, "tests", "fixtures", "verify_own_page")


class Unit(unittest.TestCase):
    def test_phone_needs_both_reads(self):
        t = "Call us 01634 757057 today"
        self.assertEqual(V.assess_phone("01634 757057", t, t, True)[0], "CONFIRMED")
        self.assertEqual(V.assess_phone("01634 757057", t, "no number", True)[0], "UNSURE")

    def test_times_need_matching_reads(self):
        a = "Collection times Tuesday 12:30 pm to 2:30 pm Wednesday Closed"
        b = "Collection times Monday Closed"
        claim = "Tuesday 12:30 pm to 2:30 pm"
        self.assertEqual(V.assess_times(claim, a, a, True)[0], "CONFIRMED")
        self.assertEqual(V.assess_times(claim, a, b, True)[0], "UNSURE")

    def test_would_blank_known_times(self):
        ours = "Thu 11:00 am to 1:00 pm"
        closed = "Monday Closed Tuesday Closed"
        self.assertTrue(V.would_blank_known_times(ours, closed))
        self.assertFalse(V.would_blank_known_times("", closed))

    def test_listing_conflict_urls(self):
        rows = [
            {"listing id": "a", "own-page URL": "https://one.example/", "phone_verdict": "CONFIRMED", "own-page phone": "01"},
            {"listing id": "a", "own-page URL": "https://two.example/", "phone_verdict": "CONFIRMED", "own-page phone": "01"},
        ]
        self.assertIn("a", V.listing_conflicts(rows))


class Integration(unittest.TestCase):
    def _run(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
            buf = io.StringIO()
            err = io.StringIO()
            old_out, old_err = sys.stdout, sys.stderr
            try:
                sys.stdout = buf
                sys.stderr = err
                V.main([path, "--fixture-dir", FIX])
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
            out = list(csv.DictReader(io.StringIO(buf.getvalue())))
            summary = err.getvalue().strip()
            return out, summary
        finally:
            os.unlink(path)

    def test_auto_apply_phone_and_times(self):
        out, summary = self._run(
            [
                {
                    "listing id": "medway-net",
                    "own-page URL": "https://example.invalid/",
                    "our phone": "01634 757056",
                    "own-page phone": "01634 757057",
                    "our times": "Thu 11:00 am to 1:00 pm",
                    "own-page times": "Thursday 9:30 am to 12:00 pm",
                }
            ]
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["phone_verdict"], "CONFIRMED")
        self.assertEqual(out[0]["times_verdict"], "CONFIRMED")
        self.assertEqual(out[0]["action"], "AUTO_APPLY")
        self.assertEqual(out[0]["review_reason"], "")
        self.assertIn("REVIEW: none", summary)

    def test_review_unstable_reads(self):
        out, summary = self._run(
            [
                {
                    "listing id": "twydall-unstable",
                    "own-page URL": "https://example.invalid/",
                    "our phone": "",
                    "own-page phone": "",
                    "our times": "Thu 9:30 am to 12:00 pm",
                    "own-page times": "Tuesday 12:30 pm to 2:30 pm",
                }
            ]
        )
        self.assertEqual(out[0]["times_verdict"], "UNSURE")
        self.assertEqual(out[0]["action"], "REVIEW")
        self.assertEqual(out[0]["review_reason"], "site down")
        self.assertIn("twydall-unstable", summary)

    def test_review_would_blank_data(self):
        out, _ = self._run(
            [
                {
                    "listing id": "all-closed",
                    "own-page URL": "https://example.invalid/",
                    "our phone": "",
                    "own-page phone": "",
                    "our times": "Thu 11:00 am to 1:00 pm",
                    "own-page times": "Monday Closed",
                }
            ]
        )
        self.assertEqual(out[0]["times_verdict"], "CONFIRMED")
        self.assertEqual(out[0]["action"], "REVIEW")
        self.assertEqual(out[0]["review_reason"], "would blank data")

    def test_review_listing_conflict(self):
        out, summary = self._run(
            [
                {
                    "listing id": "dup-id",
                    "own-page URL": "https://a.example/",
                    "our phone": "",
                    "own-page phone": "01634 757057",
                    "our times": "",
                    "own-page times": "",
                },
                {
                    "listing id": "dup-id",
                    "own-page URL": "https://b.example/",
                    "our phone": "",
                    "own-page phone": "01634 757057",
                    "our times": "",
                    "own-page times": "",
                },
            ]
        )
        self.assertTrue(all(r["action"] == "REVIEW" for r in out))
        self.assertTrue(all(r["review_reason"] == "own pages conflict" for r in out))
        self.assertIn("dup-id", summary)

    def test_review_no_number_on_page(self):
        out, _ = self._run(
            [
                {
                    "listing id": "no-phone",
                    "own-page URL": "https://example.invalid/",
                    "our phone": "020 8000 0000",
                    "own-page phone": "020 8000 1234",
                    "our times": "",
                    "own-page times": "",
                }
            ]
        )
        self.assertEqual(out[0]["phone_verdict"], "REJECTED")
        self.assertEqual(out[0]["action"], "REVIEW")
        self.assertEqual(out[0]["review_reason"], "no number or times on the page")


if __name__ == "__main__":
    unittest.main()
