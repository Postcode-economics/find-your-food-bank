"""Google Serper Nov 2026: sample of hand-checked A-grade rows in shelters_manual."""
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OV = os.path.join(ROOT, "overrides")
IDS = [
    "man-google-share-homeless-action-centre-shac",
    "man-google-crawley-open-house-hostel",
    "man-google-maggs-day-centre-worcester",
    "man-google-the-porch-oxford",
    "man-google-clock-tower-sanctuary",
]


class TestGoogleSerperSheltersNov2026(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manual = {x["id"]: x for x in json.load(open(os.path.join(OV, "shelters_manual.json"), encoding="utf-8"))}
        cls.ver = json.load(open(os.path.join(OV, "shelters_verified.json"), encoding="utf-8"))
        cls.ap = json.load(open(os.path.join(OV, "approved_new_places.json"), encoding="utf-8"))["shelters"]

    def test_sample_google_rows_present(self):
        for fid in IDS:
            self.assertIn(fid, self.manual, fid)
            self.assertIn(fid, self.ver)
            self.assertIn(fid, self.ap)

    def test_google_rows_have_phone_and_kind(self):
        for fid in IDS:
            m = self.manual[fid]
            self.assertTrue(m.get("phone"), fid)
            self.assertIn(m.get("kind"), ("hostel", "day_centre", "young_people"), fid)
            self.assertFalse(m.get("flag_closed"), fid)


if __name__ == "__main__":
    unittest.main()
