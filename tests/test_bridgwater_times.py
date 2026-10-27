"""Bridgwater Foodbank (27 Oct 2026): map showed Mon/Wed/Fri 13:00-15:30, but the own locations page
(https://bridgwater.foodbank.org.uk/locations/) lists the Mount Street Day Centre session as Mon/Wed/Fri 10:30-13:30.
Hand-reviewed protected override must hold in the override, the data files and the Somerset area page."""
import os, sys, json, unittest, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from times import normalise
WANT = {"mon": [["10:30", "13:30"]], "wed": [["10:30", "13:30"]], "fri": [["10:30", "13:30"]]}
OT = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
def full_items():
    s = open(os.path.join(ROOT, "data.full.js")).read(); return {i["id"]: i for i in json.loads(s[s.find("{"):s.rfind("}") + 1])["items"]}
class BridgwaterTimes(unittest.TestCase):
    def test_override(self):
        o = OT["bridgwater"]
        self.assertEqual(o["structured"], WANT); self.assertEqual(o["status"], "TIMES_FOUND")
        self.assertTrue(o["reader"].startswith("hand-reviewed")); self.assertNotIn("15:30", json.dumps(o))
        self.assertEqual(normalise(o)["structured"], WANT)
    def test_data_full(self):
        ot = full_items()["bridgwater"]["opening_times"]
        self.assertEqual(ot["structured"], WANT); self.assertNotIn("15:30", json.dumps(ot))
    def test_data_js(self):
        s = open(os.path.join(ROOT, "data.js")).read().rstrip().rstrip(";")
        c = json.loads(s[s.find("})(") + 3:-1])["c"]
        ot = c["opening_times"][c["id"].index("bridgwater")]
        self.assertEqual(ot["structured"], WANT); self.assertNotIn("15:30", json.dumps(ot))
class BridgwaterAreaPage(unittest.TestCase):
    def test_somerset_page(self):
        h = open(os.path.join(ROOT, "food-banks", "somerset", "index.html")).read()
        i = h.find("Bridgwater Foodbank</div>"); self.assertGreater(i, 0)
        card = h[i:h.find("</li>", i)]
        for d in ("Mon", "Wed", "Fri"): self.assertIn("<td>%s</td><td>10:30\u201313:30</td>" % d, card)
        self.assertNotIn("13:00\u201315:30", card); self.assertNotIn("15:30", card)
if __name__ == "__main__": unittest.main()
