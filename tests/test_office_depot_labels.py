"""Lock: 20 listings whose shown times were office / phone-line / depot hours, not food collection (fix/office-depot-labels, 27 Oct 2026).
Each fix comes from the organisation's own page (quoted in overrides). Nothing blanked to 'Closed'; exact food times used only where the page gives them."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from times import normalise
def J(p): return json.load(open(os.path.join(ROOT, "overrides", p), encoding="utf-8"))
def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]}
OFFICE = {  # id: (words the times text must carry, words the notice must carry)
    "york": ("Donation drop-off depot only", "not a place to collect food"),
    "glasgow-sw": ("no food parcels collected here", "no food parcels can be collected here"),
    "north-bristol-south-gloucestershire": ("Phone line hours, not collection times", "see their website for centre times"),
    "haverhill": ("Contact hours", "not food collection"),
    "luton": ("Phone line hours, not food collection", "not food collection"),
    "fusion": ("Office hours, not food collection", "office hours"),
    "aylesbury": ("deliveries and donations only", "deliveries and donations only"),
    "ek-community": ("Church office hours", "church office hours"),
    "chiltern/wendover": ("Delivery only", "Delivery only"),  # own page: delivery 'Monday-Sunday Closed'; NOT switched to Closed (held for Dean)
    "southwark": ("do NOT give out food", "no food is given out here"),
    "norwich": ("donations only", "not a place to collect food"),
    "slough": ("food cannot be collected", "food cannot be collected here"),
    "sutton": ("no food collected or distributed", "no food is collected"),
    "peterborough": ("donations and postal address only", "not a place to collect food"),
    "nuneaton": ("Postal address only", "not a place to collect food"),
}
JOINED = ("southwark", "norwich", "slough", "sutton", "peterborough", "nuneaton")  # warehouse cards no longer carry every centre's times joined
FOOD = {  # exact food times given on the own page
    "dens": {"mon": [["10:00", "13:00"]], "tue": [["10:00", "13:00"]], "wed": [["10:00", "13:00"], ["15:00", "18:00"]], "thu": [["10:00", "13:00"]], "fri": [["10:00", "13:00"]]},
    "chat": {d: [["09:30", "12:00"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat")},
    "derby-city-mission": {d: [["10:00", "12:00"]] for d in ("tue", "wed", "thu")},
    "chiltern/prestwood": {d: [["09:00", "12:00"]] for d in ("tue", "wed", "thu", "fri")},  # delivery times (Delivery only)
    "billingham-stockton-borough/stockton": {d: [["10:00", "12:00"]] for d in ("mon", "tue", "wed", "thu")},
}
class T(unittest.TestCase):
    def setUp(self): self.t, self.n, self.d = J("opening_times.json"), J("foodbank_notices.json"), items()
    def test_office_times_are_labelled_not_blanked(self):
        for k, (tw, nw) in OFFICE.items():
            o = self.t[k]
            self.assertEqual(o["status"], "TIMES_TEXT_ONLY", k); self.assertIsNone(o["structured"], k)
            self.assertIn(tw.lower(), o["raw"].lower(), k); self.assertNotIn("closed", o["raw"].lower().replace("closed every", ""), k)
            self.assertTrue(o["reader"].startswith("hand-reviewed"), k)
            self.assertIn(nw.lower(), self.n[k]["notice"].lower(), k)
            i = self.d[k]; self.assertEqual(i.get("notice"), self.n[k]["notice"], k)
            self.assertEqual(i["opening_times"]["raw"], o["raw"], k); self.assertFalse((i["opening_times"] or {}).get("structured"), k)
    def test_depot_and_office_pins_point_to_centres(self):
        m = J("foodbank_manual.json")
        self.assertEqual(m["york"]["kind"], "dropoff"); self.assertEqual(m["glasgow-sw"]["kind"], "warehouse")
        for k in ("york", "glasgow-sw", "haverhill", "luton", "fusion", "aylesbury") + JOINED:
            self.assertIn(self.d[k].get("kind"), ("warehouse", "dropoff"), k)
        for k in ("york", "glasgow-sw", "haverhill", "luton", "aylesbury") + JOINED:
            self.assertTrue(self.d[k].get("centres"), k)
    def test_exact_food_times(self):
        for k, s in FOOD.items():
            o = self.t[k]; self.assertEqual(o["status"], "TIMES_FOUND", k); self.assertEqual(o["structured"], s, k)
            self.assertTrue(o["reader"].startswith("hand-reviewed"), k)
            self.assertEqual(self.d[k]["opening_times"]["structured"], normalise(o)["structured"], k)
            self.assertNotIn(self.d[k].get("kind"), ("warehouse", "dropoff"), k)
    def test_no_joined_centre_times_on_warehouse_cards(self):
        for k in JOINED:
            raw = self.d[k]["opening_times"]["raw"]; self.assertNotIn(" | ", raw, k); self.assertNotIn("Mon Closed", raw, k)
        for c in self.d["southwark"]["centres"]:
            self.assertIn(c["id"], self.d)  # centres keep their own pins and times
    def test_prestwood_wendover_delivery_only(self):
        self.assertIn("delivery only", self.n["chiltern/prestwood"]["notice"].lower())
        self.assertNotEqual(self.d["chiltern/wendover"]["opening_times"].get("status"), "TIMES_FOUND")
if __name__ == "__main__": unittest.main()
