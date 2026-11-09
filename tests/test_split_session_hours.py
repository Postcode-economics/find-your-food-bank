"""Split sessions in one day ('10:00 - 13:00, 14:00 - 17:00', libraries closed at lunch) are valid hours.

8 Nov 2026: Canford Heath, Churchdown and Inham Nook libraries were reported "hours value invalid" for a correct
two-session day. Grok Bot 2 (9 Nov 2026): accept only valid, ordered, non-overlapping ranges, at most 3 a day, with
negative tests, no existing reject case removed, and a check that the card shows each session.
"""
import os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import recheck as R

E = {"id": "x1", "name": "Library", "postcode": "BH17 8UE", "address": "Mitchell Road", "lat": 50.75, "lng": -1.95}


def errs(v):
    return R.schema_errors(dict(E, hours={"Mon": v}), "ws")


class SplitSessions(unittest.TestCase):
    def test_real_8_nov_values_are_valid(self):
        for v in ("10:00 - 13:00, 14:00 - 17:00", "10:00 - 12:30, 14:00 - 16:30", "10:00 - 13:00, 14:00 - 18:00"):
            self.assertEqual(errs(v), [], v)

    def test_three_sessions_and_touching_sessions(self):
        self.assertEqual(errs("09:00 - 10:00, 11:00 - 12:00, 13:00 - 14:00"), [])
        self.assertEqual(errs("13:00 - 15:00, 15:00 - 17:00"), [])

    def test_negative_cases(self):
        for v in ("09:00 - 10:00, 11:00 - 12:00, 13:00 - 14:00, 15:00 - 16:00",  # more than 3
                  "14:00 - 17:00, 10:00 - 13:00",   # out of order
                  "10:00 - 13:00, 12:00 - 15:00",   # overlap
                  "13:00 - 10:00, 14:00 - 17:00",   # ends before it starts
                  "10:00 - 13:00, 14:00",           # half a range
                  "10am - 1pm, 2pm - 5pm",          # not the stored 24-hour form
                  "10:00 - 13:00, Closed",
                  "10:00 - 13:00, 14:00 - 17:00 / 18:00 - 19:00",  # mixed separators stay on the old check
                  "10:00 - 13:00,,14:00 - 17:00",
                  "25:00 - 26:00, 14:00 - 17:00"):
            self.assertTrue(errs(v), v)

    def test_existing_reject_cases_still_rejected(self):
        for v in ("1030-12", "Morning: women only", "10:00-13:00", "10:00 - 13:00 and 14:00 - 17:00", ""):
            self.assertTrue(errs(v), v)

    def test_slash_form_unchanged(self):
        # The original ' / ' check is kept exactly as it was, so nothing already published changes.
        self.assertEqual(errs("09:00 - 12:00 / 13:00 - 16:00"), [])
        self.assertEqual(errs("09:30 - 13:00 / 10:30 - 13:30"), [])  # accepted before this change too
        self.assertEqual(errs("17:00 - 10:00"), [])                   # overnight shelter, unchanged
        self.assertTrue(errs("09:00 - 12:00 / 1pm"))

    def test_card_shows_each_session(self):
        # Design-lock check: the card cell turns 'HH:MM - HH:MM' into 'HH:MM-HH:MM' for every session in the value,
        # so both sessions appear in one Mon row. Read the live regex from layers.js so a change to it fails here.
        js = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        self.assertIn(r".replace(/(\d\d:\d\d) - (\d\d:\d\d)/g,'$1-$2')", js)
        shown = re.sub(r"(\d\d:\d\d) - (\d\d:\d\d)", r"\1-\2", "10:00 - 13:00, 14:00 - 17:00")
        self.assertEqual(shown, "10:00-13:00, 14:00-17:00")


if __name__ == "__main__":
    unittest.main()
