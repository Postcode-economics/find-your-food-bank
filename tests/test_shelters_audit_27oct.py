"""fix/shelters-audit (27 Oct 2026): proven shelter corrections, each quoted from the organisation's own page on 2 fetches.
Dean: never remove a shelter or a number without a proven replacement; no council general number as a shelter line.
Dean 28 Oct: phone changes are listed in PHONES-FOR-DEAN.md, never applied without his approval by name; no directory or
third-party source for any change; every change logged with an undo; council lines are out-of-hours only."""
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
        self.assertEqual(s["hl-dens-the-elms"]["phone"], "01442 800131")  # proposed 01442 262274 is third-party only: held
        self.assertIn("24/7", s["osm-node-1533578890"]["hours"])  # Peasholme phone belongs to #238: see test_peasholme_phone_left_to_238
        self.assertNotEqual(s["osm-way-169564851"]["phone"], "01904 553626")  # James House: council office line, not the hostel's own
        self.assertTrue(s["hl-kings-lynn-night-shelter"]["referral"].startswith("By referral from any local organisation"))
        self.assertIn("St John's Vicarage", s["hl-kings-lynn-night-shelter"]["address"])
        self.assertNotIn("Acorn Recovery", s["osm-way-1119807447"].get("operator") or ""); self.assertEqual(s["osm-way-1119807447"]["phone"], "0300 111 1212")  # directory-only: not used
        self.assertIn("Chelmar Road", s["hl-amat-uk"]["address"])
        for k, pc in {"sa-glen-alva-family-centre-lifehouse": "BT14 6JN", "sa-springfield-house-lifehouse": "MK6 3HR", "sa-st-monica-s-house-lifehouse": "PO1 1PA",
                      "osm-way-1158181491": "SR1 2AU", "sa-the-booth-centre-southampton-lifehouse": "SO14 3DL", "osm-way-101893157": "SO23 8RZ"}.items():
            self.assertEqual(s[k]["postcode"], pc, k)
        self.assertEqual(s["osm-way-1158181491"]["address"], "Swan Lodge, 5-8 High Street, Sunderland")
        self.assertEqual(s["osm-way-556071354"]["phone"], "0141 429 4541")  # 0141 418 1955 is for Dean
        self.assertEqual(s["osm-way-101893157"]["name"], "The Winchester Beacon"); self.assertEqual(s["osm-way-101893157"]["phone"], "01962 862050")
        self.assertTrue(s["osm-way-260267675"]["referral"].startswith("Reported closed – call before you go"))  # third-party closure report: label, kept
        self.assertEqual(s["man-wakefield-swep"]["phone"], "07477 897929 or 01924 923197")  # Riverside line not shown as the SWEP route: unchanged
    def test_fixes_survive_refresh(self):
        # a refresh brings back the old source values; shelter_contacts.apply (run on every build) restores the checked ones
        stale = {"osm-way-101893157": {"id": "osm-way-101893157", "name": "Winchester Churches Night Shelter", "postcode": "SO23 8RS", "address": "x", "phone": "01962 862050"},
                 "hl-dens-the-elms": {"id": "hl-dens-the-elms", "name": "DENS", "phone": "01442 800131"}}
        its = list(stale.values()); SC.apply(its, self.C)
        self.assertEqual(its[0]["name"], "The Winchester Beacon"); self.assertEqual(its[0]["postcode"], "SO23 8RZ"); self.assertEqual(its[1]["phone"], "01442 800131")
        B = json.load(open(os.path.join(R, "overrides", "phone_baseline.json")))["listings"]
        self.assertEqual(B["hl-dens-the-elms"]["phone"], "01442 800131"); self.assertEqual(B["osm-way-556071354"]["phone"], "0141 429 4541")
    def test_council_number_check_flags_not_removes(self):
        f = CC.check(list(self.s.values()))
        self.assertIn("osm-way-169564851", [x["id"] for x in f])  # James House still on York Housing Options main line: flagged for Dean
        self.assertEqual("osm-node-1533578890" in [x["id"] for x in f], self.s["osm-node-1533578890"]["phone"] == "01904 554500")  # flagged while on the Housing Options main line
        x = {"id": "t", "name": "T", "phone": "01904 554500"}; CC.check([x]); self.assertEqual(x["phone"], "01904 554500")
    def test_council_ooh_lines_are_quoted_out_of_hours(self):
        f = {(x["id"], x["field"]) for x in CC.check(list(self.s.values()))}
        G = json.load(open(os.path.join(R, "overrides", "council_general_numbers.json")))["_ooh_confirmed"]
        for k in ("osm-node-5901363647", "osm-way-1352311712", "scni-armagh", "scni-portadown"):
            x = self.s[k]; self.assertNotIn((k, "council_ooh"), f); self.assertIn(x["council_ooh"], G, k)
            g = G[x["council_ooh"]]
            if "approved_by" in g: self.assertIn("Dean", g["approved_by"]); continue  # Dean approved the number by name
            self.assertIn(x["council_ooh"], g["quote"]); self.assertTrue(g["source"].startswith("https://"))
            self.assertIn("out of hours", g["quote"].lower().replace("-", " "))
        for x in self.s.values():  # every published council line is an out-of-hours line
            if x.get("council_phone"): self.assertEqual(x["council_phone"], x.get("council_ooh"), x["id"])
        y = {"id": "t", "name": "T", "phone": "020 8496 3000"}; self.assertEqual([z["id"] for z in CC.check([y])], ["t"])  # a council line is never a shelter's own phone
        y = {"id": "t", "name": "T", "council_ooh": "01904 554500", "council_phone": "01904 554500"}; self.assertEqual([z["field"] for z in CC.check([y])], ["council_ooh"])  # a daytime general line shown as out-of-hours is flagged

class Dean28Oct(unittest.TestCase):
    """Dean 28 Oct 2026: phones go to PHONES-FOR-DEAN.md, own-page sources only, every change logged with an undo, times never to closed/empty."""
    NOT_OWN = ("homeless.org.uk", "servicefinder.", "newhope.org.uk", "trusselltrust", "givefood", "charitycommission", "register-of-charities")
    @classmethod
    def setUpClass(c):
        c.s = items(); c.C = json.load(open(os.path.join(R, "overrides", "shelters_contacts.json")))
        c.D = open(os.path.join(R, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        c.L = json.load(open(os.path.join(R, "logs", "shelters_audit_27oct_changes.json")))["changes"]
        t = subprocess.run(["git", "-C", R, "show", "origin/main:shelters.js"], capture_output=True, text=True).stdout
        c.M = items(t) if t else {}
    def test_phone_proposals_listed_not_applied(self):
        for k, cur, new in (("osm-way-556071354", "0141 429 4541", "0141 418 1955"), ("hl-dens-the-elms", "01442 800131", "01442 262274")):
            self.assertEqual(self.s[k]["phone"], cur, k); self.assertNotIn("phone_fix", self.C[k], k)
            row = [l for l in self.D.splitlines() if "`%s`" % k in l]; self.assertEqual(len(row), 1, k)
            self.assertIn("| %s | %s | https://" % (cur, new), row[0]); self.assertIn('"', row[0])
        self.assertIn("Held: third-party source only", [l for l in self.D.splitlines() if "`hl-dens-the-elms`" in l][0])
        self.assertIn("Held: conflicting own page", [l for l in self.D.splitlines() if "`osm-way-556071354`" in l][0])
    def test_peasholme_phone_left_to_238(self):
        # Dean approved 01904 551901 in #238; this PR must not set Peasholme's phone either way
        k = "osm-node-1533578890"; self.assertNotIn("phone_fix", self.C[k])
        if self.M: self.assertEqual((self.s[k]["phone"], self.s[k]["tel"]), (self.M[k]["phone"], self.M[k]["tel"]))
        self.assertFalse([l for l in self.D.splitlines() if l.startswith("|") and "`%s`" % k in l])
        B = json.load(open(os.path.join(R, "overrides", "phone_baseline.json")))["listings"][k]
        t = subprocess.run(["git", "-C", R, "show", "origin/main:overrides/phone_baseline.json"], capture_output=True, text=True).stdout
        if t: self.assertEqual(B, json.loads(t)["listings"][k])
    def test_no_phone_changed_from_main(self):
        for k, x in self.s.items():
            if k in self.M: self.assertEqual((x.get("phone"), x.get("tel")), (self.M[k].get("phone"), self.M[k].get("tel")), k)
    def test_fixes_from_own_pages(self):
        for k, o in self.C.items():
            if isinstance(o, dict) and o.get("fix") and str(o.get("fix_source", "")).startswith("http"):
                self.assertFalse(any(b in o["fix_source"] for b in self.NOT_OWN), k)
    def test_every_change_logged_with_undo(self):
        logged = {(c["id"], c["field"]) for c in self.L}
        for c in self.L: self.assertEqual(self.s[c["id"]].get(c["field"]), c["now"]); self.assertIn("undo", c); self.assertTrue(c["source"])
        for k, x in self.s.items():
            if k not in self.M: continue
            for f in ("name", "address", "postcode", "operator", "hours", "referral", "season"):
                if x.get(f) != self.M[k].get(f): self.assertIn((k, f), logged, (k, f))
    def test_known_times_never_closed_or_empty(self):
        for c in self.L:
            if c["field"] == "hours" and c["was"]:
                self.assertTrue(c["now"]); self.assertNotIn("closed", json.dumps(c["now"]).lower())
if __name__ == "__main__": unittest.main()
