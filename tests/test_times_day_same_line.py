"""Dean 27 Oct 2026 07:20 (strict auto-apply): the day must be on the same line as its times on the own-site page."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover

class DaySameLine(unittest.TestCase):
    def test_day_next_to_times_passes(self):
        st = {"tue": [["10:00", "12:00"]], "thu": [["13:00", "15:00"]]}
        self.assertTrue(discover.day_same_line(st, ["Open Tuesday 10am - 12pm and Thursday 1pm - 3pm. AB1 2CD"]))
    def test_range_covers_days_between(self):
        st = {d: [["09:00", "12:00"]] for d in ("mon", "tue", "wed")}
        self.assertTrue(discover.day_same_line(st, ["Mon - Wed 9am - 12pm"]))
    def test_days_and_times_apart_is_held(self):
        st = {"tue": [["10:00", "12:00"]]}
        self.assertFalse(discover.day_same_line(st, ["We open on Tuesday. Times: 10am - 12pm"]))
    def test_wrong_time_for_day_is_held(self):
        st = {"tue": [["10:00", "12:00"]]}
        self.assertFalse(discover.day_same_line(st, ["Tuesday 1pm - 3pm"]))
    def test_gate_reason_blocks(self):
        i = {"id": "x", "postcode": "AB1 2CD", "website": "https://ex.org", "opening_times": {"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "10:00"]]}}}
        new = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}}
        why = discover.times_gate_reasons(i, "fb", "opening_times", new, ["AB1 2CD We open on Tuesday. Times: 10am - 12pm"],
                                          {"final_url": "https://ex.org/visit"}, {}, {}, True, "r2")
        self.assertIn("day not on the same line as its times on the own-site page", why)

if __name__ == "__main__": unittest.main()
