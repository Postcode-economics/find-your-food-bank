"""First Base (Dumfriesshire) emergency parcel pick-up points (Dean, 25 Oct 2026): hours from First Base's
'Get Help Now' page (hand-reviewed, protected from robots), card label, First Base number tag, Dalbeattie added,
Castle Douglas Citizens Advice moved. All via overrides, so every refresh keeps them."""
import os, sys, json, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
J = lambda f: json.load(open(os.path.join(ROOT, "overrides", f)))
P = "first-base-dumfriesshire"
SUBS = ["citizens-advice-castle-douglas", "kelloholm-library-sanquhar", "sanquhar-library-sanquhar", "clarks-little-ark", "thornhill-library",
        "dalbeattie-customer-services", "citizens-advice-annan", "kates-kitchen", "social-work-department-annan", "gretna-library",
        "lockerbie-library", "moffat-library", "langholm-library"]
SRC = "https://www.firstbasedumfries.co.uk/contact-us/"
CA = "https://www.dagcas.org/dagcas-location/castle-douglas-cab/"  # Dean 07:48: Castle Douglas hours from Citizens Advice's own page

class Overrides(unittest.TestCase):
    def test_thirteen_points_labelled(self):
        n, l = J("foodbank_notices.json"), J("phone_labels.json")
        self.assertEqual(len(SUBS), 13)
        for s in SUBS:
            k = f"{P}/{s}"
            self.assertTrue(n[k]["notice"].startswith("First Base emergency parcel pick-up point"), k)
            self.assertEqual(l[k], "First Base number", k)
    def test_hours_protected_and_sourced(self):
        o = J("opening_times.json"); x = J("foodbank_extra_locations.json")
        for s in [None] + SUBS:
            k = P if s is None else f"{P}/{s}"
            ot = x[k]["opening_times"] if k in x else o[k]
            self.assertEqual(ot["source_url"], CA if s == "citizens-advice-castle-douglas" else SRC); self.assertEqual(ot["status"], "TIMES_FOUND")
            self.assertTrue(ot["reader"].startswith("hand-reviewed"), k)
        self.assertEqual(o[P]["structured"], {d: [["12:00", "14:00"]] for d in ("mon", "tue", "wed", "thu", "fri")})
        self.assertEqual(o[f"{P}/moffat-library"]["structured"], {"tue": [["10:00", "19:00"]], "fri": [["09:00", "17:00"]], "sat": [["09:00", "12:00"]]})
        h = [["10:00", "12:30"], ["13:00", "16:00"]]
        self.assertEqual(o[f"{P}/citizens-advice-castle-douglas"]["structured"], {"wed": h, "fri": h})
        self.assertEqual(o[f"{P}/kates-kitchen"]["structured"], {"tue": [["11:00", "14:00"]], "thu": [["11:00", "14:00"]]})
    def test_applied_by_classify(self):
        import classify
        par = {"id": P, "type": "foodbank", "name": "First Base (Dumfriesshire) Foodbank", "phone": "01387279680", "address": "6 Buccleuch Street, Dumfries, DG1 2AH", "postcode": "DG1 2AH", "lat": 55.06927, "lng": -3.61619}
        cd = {"id": f"{P}/citizens-advice-castle-douglas", "type": "location", "name": "Citizens Advice Castle Douglas", "address": "3 St Andrew Street, Castle Douglas, DG7 1DE", "postcode": "DG7 1DE", "lat": 54.93929, "lng": -3.93295}
        items = [par, cd]
        classify.add_extra_locations(items, ROOT); classify.apply_address_fixes(items, ROOT)
        d = next(i for i in items if i["id"] == f"{P}/dalbeattie-customer-services")
        self.assertEqual((d["postcode"], d["phone"], d["foodbank"]), ("DG5 4AD", "01387279680", par["name"]))
        c = next(i for i in items if i["id"] == cd["id"])
        self.assertEqual(c["postcode"], "DG7 1EG"); self.assertIn("Queen Street", c["address"])
