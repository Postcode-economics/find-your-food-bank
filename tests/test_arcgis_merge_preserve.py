"""ArcGIS merge must not wipe tier-2 / hand fields on existing warm-space rows."""
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import arcgis_warmspaces as A

FIX = os.path.join(ROOT, "tests", "fixtures")


def feed(fid):
    return next(f for f in A.load_config() if f["id"] == fid)


class MergePreserve(unittest.TestCase):
    def test_keeps_provided_and_sign_url(self):
        fresh = [{
            "id": "ww-65442002",
            "name": "Renew QE Park",
            "postcode": "GU2 9LX",
            "provided": ["Hot Drinks", "Free Wifi"],
            "sign_url": "https://www.qeparkbaptist.org.uk/Groups/372127/Renew_QE_Park.aspx",
            "tier": "unverified",
            "hours": {"Wed": "12:00 - 14:00"},
        }]
        rec = {
            "id": "ww-65442002",
            "name": "Renew QE Park",
            "postcode": "GU2 9LX",
            "provided": [],
            "hours": {"Wed": "12:00 - 14:00", "Thu": "10:00 - 12:00"},
            "source_url": "https://example.com/feed",
        }
        A.merge_records(fresh, [rec])
        row = fresh[0]
        self.assertEqual(row["provided"], ["Hot Drinks", "Free Wifi"])
        self.assertEqual(row["sign_url"], "https://www.qeparkbaptist.org.uk/Groups/372127/Renew_QE_Park.aspx")
        self.assertEqual(row["tier"], "unverified")
        self.assertIn("Thu", row["hours"])

    def test_clean_phone_strips_bidi_marks(self):
        self.assertEqual(A._clean_phone("01608\u202c737315"), "01608737315")

    def test_clean_address_strips_junk_prefix(self):
        self.assertEqual(A._clean_address("STREET RECORD, 1 High St"), "1 High St")

    def test_malformed_website_uses_council_page(self):
        fb = feed("cherwell")
        self.assertEqual(A._feed_website("not a url", fb), fb["website"])


if __name__ == "__main__":
    unittest.main()
