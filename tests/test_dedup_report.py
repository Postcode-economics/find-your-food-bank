import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import dedup_report as D
class T(unittest.TestCase):
    def test_pairs(self):
        it = [dict(id="a", name="Risca Foodbank", postcode="NP11 6AA", lat=51.6, lng=-3.1), dict(id="b", name="Risca", postcode="np116aa", lat=51.6, lng=-3.1001),
              dict(id="c", name="Hope Kitchen", postcode="NP11 6AA", lat=51.61, lng=-3.12), dict(id="d", name="Other", postcode="XX1 1XX", lat=1, lng=1)]
        k = {(p["a"], p["b"]): p["kind"] for p in D.find(it)}
        self.assertEqual(k[("a", "b")], "likely duplicate"); self.assertEqual(k[("a", "c")], "same postcode, different service"); self.assertEqual(len(k), 3)
