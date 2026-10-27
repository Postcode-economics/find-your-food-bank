"""Cardiff Foodbank (27 Oct 2026): every centre showed Mon-Fri 09:30-13:30, the phone-line hours printed on every centre
card. Hand-checked times per centre card (saved page tests/fixtures/cardiff_voucher_2026-10-27.html.txt) must hold, and the
3x-daily refresh cross-check must never put the wrong times back."""
import os, sys, json, copy, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, classify as C
from times import normalise
HTML = open(os.path.join(ROOT, "tests", "fixtures", "cardiff_voucher_2026-10-27.html.txt")).read()
URL = "https://cardiff.foodbank.org.uk/emergency-food/i-have-a-food-voucher"
OT = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
WANT = {"cathays": {"tue": [["13:00", "15:00"]], "sat": [["11:00", "13:00"]]}, "central": {"thu": [["10:00", "12:00"]]},
        "ely": {"mon": [["13:00", "15:00"]], "thu": [["13:00", "15:00"]]}, "grangetown": {"fri": [["12:00", "14:00"]]},
        "llanedeyrn": {"wed": [["13:00", "15:00"]], "fri": [["11:30", "13:30"]]},
        "splott": {"wed": [["13:00", "15:00"]], "thu": [["18:30", "20:00"]]}, "st-mellons": {"mon": [["12:30", "14:30"]]},
        "tongwynlais": {"wed": [["14:00", "16:00"]]}}
def data_items():
    s = open(os.path.join(ROOT, "data.full.js")).read(); return json.loads(s[s.find("{"):s.rfind("}") + 1])["items"]
class CardiffTimes(unittest.TestCase):
    def test_overrides(self):
        for k, st in WANT.items():
            o = OT["cardiff/" + k]
            self.assertEqual(o["structured"], st, k); self.assertEqual(o["status"], "TIMES_FOUND")
            self.assertNotIn("09:30", json.dumps(o)); self.assertTrue(o["reader"].startswith("hand-reviewed"))
            self.assertEqual(normalise(o)["structured"], st)
        self.assertNotIn("cardiff", OT)   # Titan Road warehouse: office hours only, not a collection point
    def test_data(self):
        it = {i["id"]: i for i in data_items()}
        for k, st in WANT.items(): self.assertEqual(it["cardiff/" + k]["opening_times"]["structured"], st, k)
        self.assertFalse(it["cardiff"].get("opening_times")); self.assertEqual(it["cardiff"].get("kind"), "warehouse")
        self.assertEqual(it["cardiff/central"]["postcode"], "CF11 6LU"); self.assertEqual(it["cardiff/tongwynlais"]["postcode"], "CF15 7NS")
    def test_refresh_cannot_revert(self):
        def fetcher(u): return {"http": 200, "final_url": u, "html": HTML, "sha256": "x"}
        items = [{"id": "cardiff/" + k, "name": k.replace("-", " ").title(), "postcode": "CF11 6LU", "website": "https://cardiff.foodbank.org.uk",
                  "opening_times": dict(copy.deepcopy(OT["cardiff/" + k]))} for k in WANT]
        D.cross_check_times(items, "fb", "opening_times", fetcher=fetcher, threads=1)
        for i in items: self.assertEqual(i["opening_times"]["structured"], WANT[i["id"].split("/")[1]], i["id"])
    def test_pins_moved(self):
        items = [{"id": "cardiff/central", "type": "location", "address": "x CF11 9AD", "postcode": "CF11 9AD", "lat": 51.481403, "lng": -3.1884244},
                 {"id": "cardiff/tongwynlais", "type": "location", "address": "x CF15 7LG", "postcode": "CF15 7LG", "lat": 51.5320648, "lng": -3.2523405}]
        C.apply_address_fixes(items, ROOT)
        self.assertIn("3 Lower Cathedral Road", items[0]["address"]); self.assertEqual(items[0]["postcode"], "CF11 6LU")
        self.assertEqual(items[1]["postcode"], "CF15 7NS")
        for i in items: self.assertIn(i["postcode"], D.text_of(HTML))
if __name__ == "__main__": unittest.main()
