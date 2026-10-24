import datetime, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import holidays as h
BH = {"england-and-wales": [{"title": "Christmas Day", "date": "2026-12-25"}], "scotland": [{"title": "St Andrew's Day", "date": "2026-11-30"}], "northern-ireland": []}
class T(unittest.TestCase):
    def test_nation(self): self.assertEqual([h.nation(p) for p in ("BT1 1AA", "G1 1AA", "GL1 1AA", "EH1 1AA")], ["northern-ireland", "scotland", "england-and-wales", "scotland"])
    def test_ahead(self):
        self.assertEqual(len(h.holiday_ahead({"postcode": "SW1A 1AA"}, datetime.date(2026, 12, 20), BH)), 1)
        self.assertEqual(h.holiday_ahead({"postcode": "SW1A 1AA"}, datetime.date(2026, 11, 25), BH), [])
        self.assertEqual(len(h.holiday_ahead({"postcode": "G1 1AA"}, datetime.date(2026, 11, 25), BH)), 1)
    def test_text(self): self.assertEqual(h.holiday_text({"opening_times": {"lines": ["Mon 10-12", "Closed bank holidays"]}}), ["Closed bank holidays"])
    def test_filter_past(self): self.assertEqual(h.bank_holidays({"x": {"events": [{"date": "2020-01-01"}, {"date": "2030-01-01"}]}}, datetime.date(2026, 1, 1)), {"x": [{"date": "2030-01-01"}]})
