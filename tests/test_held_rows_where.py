"""9 Nov 2026: held rows carry postcode and pin (private logs/ only) so the city watch can place them.
Before this, 5,520 'read failed' rows had no postcode and all counted as unlocated."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common, city_watch as C

G = {"name": "Glasgow", "lat": 55.8642, "lng": -4.2518}


class Where(unittest.TestCase):
    def test_postcode_and_pin_copied(self):
        self.assertEqual(common._where({"postcode": "G1 1AA", "lat": 55.86, "lng": -4.25}),
                         {"postcode": "G1 1AA", "lat": 55.86, "lng": -4.25})

    def test_no_pin_and_bad_values_not_copied(self):
        self.assertEqual(common._where({"postcode": "G1 1AA", "lat": 55.86, "lng": -4.25, "no_pin": True}), {"postcode": "G1 1AA"})
        self.assertEqual(common._where({"lat": "55.8", "lng": None}), {})
        self.assertEqual(common._where({}), {})


class Fallback(unittest.TestCase):
    def test_outcode_still_wins(self):
        b, un = C.near_outcode([{"postcode": "G1 1AA", "lat": 51.5, "lng": -0.12}], [G], {"G1": [55.86, -4.25]})
        self.assertEqual((len(b["Glasgow"]), un), (1, 0))

    def test_pin_used_when_no_outcode(self):
        b, un = C.near_outcode([{"postcode": "", "lat": 55.86, "lng": -4.25}], [G], {})
        self.assertEqual((len(b["Glasgow"]), un), (1, 0))

    def test_nothing_known_still_unlocated(self):
        b, un = C.near_outcode([{"postcode": ""}, {"lat": "x", "lng": 1}], [G], {})
        self.assertEqual((len(b["Glasgow"]), un), (0, 2))


if __name__ == "__main__":
    unittest.main()
