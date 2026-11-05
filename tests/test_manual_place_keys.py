"""build_shelters reads x["postcode"], x["lat"], x["lng"] on every manual record: the keys must exist
(no_pin records keep them empty: postcode "" and lat/lng null, never a value)."""
import json, os, unittest
P = os.path.join(os.path.dirname(__file__), "..", "overrides", "shelters_manual.json")
class Keys(unittest.TestCase):
    def test_keys_present_and_no_pin_empty(self):
        for r in json.load(open(P, encoding="utf-8")):
            for k in ("postcode", "lat", "lng"):
                self.assertIn(k, r, (r["id"], k))
            if r.get("no_pin") and r["id"].startswith("man-ss-"):
                self.assertEqual((r["postcode"], r["lat"], r["lng"]), ("", None, None), r["id"])
if __name__ == "__main__":
    unittest.main()
