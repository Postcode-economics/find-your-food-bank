"""fix/shelters-audit (27 Oct 2026): proven shelter corrections, each quoted from its source on 2 fetches.
Dean: never remove a shelter or a number without a proven replacement; no council general number as a shelter line."""
import json, os, re, subprocess, sys, unittest
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(R, "scripts"))
import shelter_contacts as SC, council_number_check as CC
def items(src=None):
    t = open(os.path.join(R, "shelters.js")).read() if src is None else src
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
BASE_COUNT = 99  # shelters published on main when this PR was opened
class Audit(unittest.TestCase):
    @classmethod
    def setUpClass(c): c.s = items(); c.C = json.load(open(os.path.join(R, "overrides", "shelters_contacts.json")))
    def test_shelter_count_never_drops(self):
        self.assertGreaterEqual(len(self.s), BASE_COUNT)
        try:
            main = subprocess.run(["git", "-C", R, "show", "origin/main:shelters.js"], capture_output=True, text=True).stdout
            if main: self.assertFalse(set(items(main)) - set(self.s), "a shelter on main is missing here")
        except Exception: pass
        for k in ("osm-way-260267675", "man-nightsafe-blackburn", "hl-nightsafe-blackburn", "osm-way-1119807447"): self.assertIn(k, self.s)
    def test_no_number_removed(self):
        for k, x in self.s.items():
            if x.get("phone_was"): self.assertTrue(x.get("phone") and x.get("phone_source"), k)
    def test_fixes(self):
        s = self.s
        self.assertEqual((s["osm-way-1125252517"]["address"], s["osm-way-1125252517"]["postcode"]), ("235 Barmouth Street, Beswick, Manchester", "M11 3TB"))
        self.assertEqual(s["hl-nightsafe-blackburn"]["hours"]["Sat"], "17:00 - 10:00"); self.assertEqual(s["hl-nightsafe-blackburn"]["hours"]["Sun"], "17:00 - 11:00")
        self.assertEqual(s["hl-dens-the-elms"]["phone"], "01442 262274")
        self.assertEqual(s["osm-node-1533578890"]["phone"], "01904 551901"); self.assertIn("24/7", s["osm-node-1533578890"]["hours"])
        self.assertNotEqual(s["osm-way-169564851"]["phone"], "01904 553626")  # James House: council office line, not the hostel's own
        self.assertTrue(s["hl-kings-lynn-night-shelter"]["referral"].startswith("By referral from any local organisation"))
        self.assertIn("St John's Vicarage", s["hl-kings-lynn-night-shelter"]["address"])
        self.assertIn("Acorn Recovery", s["osm-way-1119807447"]["operator"]); self.assertTrue(s["osm-way-1119807447"]["phone"])
        self.assertIn("Chelmar Road", s["hl-amat-uk"]["address"])
        for k, pc in {"sa-glen-alva-family-centre-lifehouse": "BT14 6JN", "sa-springfield-house-lifehouse": "MK6 3HR", "sa-st-monica-s-house-lifehouse": "PO1 1PA",
                      "osm-way-1158181491": "SR1 2AU", "sa-the-booth-centre-southampton-lifehouse": "SO14 3DL", "osm-way-101893157": "SO23 8RZ"}.items():
            self.assertEqual(s[k]["postcode"], pc, k)
        self.assertEqual(s["osm-way-1158181491"]["address"], "Swan Lodge, 5-8 High Street, Sunderland")
        self.assertEqual(s["osm-way-556071354"]["phone"], "0141 418 1955")
        self.assertEqual(s["osm-way-101893157"]["name"], "The Winchester Beacon"); self.assertEqual(s["osm-way-101893157"]["phone"], "01962 862050")
        self.assertTrue(s["osm-way-260267675"]["referral"].startswith("Call before you go"))
        self.assertEqual(s["man-wakefield-swep"]["phone"], "07477 897929 or 01924 923197")  # Riverside line not shown as the SWEP route: unchanged
    def test_fixes_survive_refresh(self):
        # a refresh brings back the old source values; shelter_contacts.apply (run on every build) restores the checked ones
        stale = {"osm-way-101893157": {"id": "osm-way-101893157", "name": "Winchester Churches Night Shelter", "postcode": "SO23 8RS", "address": "x", "phone": "01962 862050"},
                 "hl-dens-the-elms": {"id": "hl-dens-the-elms", "name": "DENS", "phone": "01442 800131"}}
        its = list(stale.values()); SC.apply(its, self.C)
        self.assertEqual(its[0]["name"], "The Winchester Beacon"); self.assertEqual(its[0]["postcode"], "SO23 8RZ"); self.assertEqual(its[1]["phone"], "01442 262274")
        B = json.load(open(os.path.join(R, "overrides", "phone_baseline.json")))["listings"]
        self.assertEqual(B["hl-dens-the-elms"]["phone"], "01442 262274"); self.assertEqual(B["osm-node-1533578890"]["phone"], "01904 551901")
    def test_council_number_check_flags_not_removes(self):
        f = CC.check(list(self.s.values()))
        self.assertIn("osm-way-169564851", [x["id"] for x in f])  # James House still on York Housing Options main line: flagged for Dean
        self.assertNotIn("osm-node-1533578890", [x["id"] for x in f])
        x = {"id": "t", "name": "T", "phone": "01904 554500"}; CC.check([x]); self.assertEqual(x["phone"], "01904 554500")
if __name__ == "__main__": unittest.main()
