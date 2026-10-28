"""Listings batch #239 (28 Oct 2026): proven own-page fixes, labels, and Dean-approved removals. Undo log: logs/listings_batch_28oct.json."""
import json, os, re, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
def J(p): return json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
REMOVED = ("salvation-army/blackburn", "salvation-army/saltcoats", "salvation-army/teignmouth", "luton/marsh-farm")
class Removals(unittest.TestCase):
    def test_removed_and_excluded_with_reason(self):
        d = items(); ex = {e["slug"]: e for e in J("overrides/foodbank_exclude.json")["foodbanks"]}
        for i in REMOVED:
            self.assertNotIn(i, d); self.assertTrue(ex[i]["exact"]); self.assertTrue(ex[i]["reason"].strip())
    def test_refresh_cannot_bring_back(self):
        src = open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8").read()
        self.assertIn("foodbank_exclude.json", src)
        ex = J("overrides/foodbank_exclude.json")["foodbanks"]
        def excluded(i):
            return any(i == e["slug"] or (not e.get("exact") and i.startswith(e["slug"] + "/")) for e in ex)
        for i in REMOVED: self.assertTrue(excluded(i))
        self.assertFalse(excluded("salvation-army/blackburn-citadel-x"))  # exact: nothing else dropped
    def test_undo_logged(self):
        L = J("logs/listings_batch_28oct.json")["changes"]
        for i in REMOVED:
            e = [l for l in L if l["kind"] == "removed" and l["id"] == i][0]
            self.assertEqual(e["old"]["id"], i)
class Labels(unittest.TestCase):
    def test_review_section_survives_refresh(self):
        self.assertIn("'listings batch 28 oct'", open(os.path.join(ROOT, "scripts", "publish_gate.py")).read())
        pd = open(os.path.join(ROOT, "reports", "pending_dean.md")).read()
        self.assertIn("<!-- listings batch 28 oct -->", pd); self.assertIn("salvation-army/blackburn", pd)
    def test_reported_closed_kept_with_label(self):
        d = items()
        for i in ("salvation-army/southend-southchurch", "salvation-army/lochgelly", "salvation-army/thornaby",
                  "salvation-army/midsomer-norton", "salvation-army/west-cornforth", "salvation-army/wandsworth"):
            self.assertIn(i, d); self.assertTrue(d[i]["notice"].startswith("Reported closed, call before you go"), i)
            self.assertNotIn("Closed:", d[i]["notice"])
    def test_morley_and_delivery_only(self):
        d = items()
        self.assertTrue(d["salvation-army/morley"]["notice"].startswith("Leeds South & East Foodbank, voucher needed"))
        for i in ("devizes-district/pewsey", "devizes-district/marlborough"): self.assertTrue(d[i]["notice"].startswith("Delivery only"))
class Fixes(unittest.TestCase):
    def test_phones(self):
        d = items(); dg = lambda s: re.sub(r"\D", "", s or "")
        # Dean 28 Oct 06:37: phone changes wait for Dean. Current number stays; the proposal is listed in PHONES-FOR-DEAN.md.
        exp = {"scunthorpe/epworth-baptist-church": ("01427875839", "03001028061"), "aberdeen-south": ("07360162919", "01224569750"),
               "leominster": ("07715410575", "07563000862"), "3food4u": ("01992842642", "07973166940"), "st-monicas": ("02077989025", "02088869568"),
               "salvation-army/alton": ("0142084456", "01420541778"), "salvation-army/st-austell": ("0172661791", "01726890174"),
               "stroud-district/dursley": ("03001023254", "01453367077"), "rickmansworth/abbots-langley": ("03442451296", "07716856892"),
               "shepway/lydd": ("01797320345", "07913573403")}
        P = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        L = J("logs/listings_batch_28oct.json")["changes"]
        B = J("overrides/phone_baseline.json")["listings"]; O = J("overrides/phones.json")
        for i, (cur, prop) in exp.items():
            self.assertEqual(dg(d[i]["phone"]), cur, i); self.assertEqual(dg(B[i]["phone"]), cur, i)
            self.assertNotEqual(dg(O.get(i)), prop, i)
            self.assertFalse(d[i].get("phone_label"), i)
            self.assertIn("| `%s` " % i, P); self.assertIn("| %s |" % prop, P)
            self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "phone" and l["note"].startswith("reverted") and dg(l["undo"]["set"]["phone"]) == prop], i)
        self.assertFalse(d["andover/test-valley-borough-council-office"]["phone"])  # council switchboard removed, listing kept
        self.assertIn("andover/test-valley-borough-council-office", P)
        self.assertNotEqual(dg(d["salvation-army/andover"]["phone"]), "01264335242")  # charity shop line not applied
    def test_only_dean_approved_phones_changed(self):
        d = items(); dg = lambda s: re.sub(r"\D", "", s or "")
        self.assertEqual(dg(d["whitby"]["phone"]), "01947469004"); self.assertEqual(dg(d["whitby"]["tel"]), "01947469004")
        self.assertEqual(J("overrides/phone_baseline.json")["listings"]["whitby"]["phone"], "01947469004")
        self.assertTrue([l for l in J("logs/listings_batch_28oct.json")["changes"] if l["id"] == "whitby" and l["kind"] == "phone" and dg(l["undo"]["set"]["phone"]) == "07789765696"])
        def layer(f):
            t = open(os.path.join(ROOT, f), encoding="utf-8").read(); return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
        S, W = layer("shelters.js"), layer("warmspaces.js")
        self.assertEqual(dg(S["osm-way-169564851"]["phone"]), "01904553626")  # James House, Dean approved
        self.assertFalse(W["ww-68618605"].get("phone"))  # Bruton council switchboard removal, Dean approved
        for i, n in (("hl-dens-the-elms", "01442800131"), ("osm-way-556071354", "01414294541")): self.assertEqual(dg(S[i]["phone"]), n, i)
        self.assertEqual(dg(W["ww-57951889"]["phone"]), "07821153701")
        # reverting these would put a general council line back on the venue (rule 5): kept, listed for Dean
        self.assertEqual(dg(S["osm-node-1533578890"]["phone"]), "01904551901"); self.assertEqual(dg(W["ww-55475981"]["phone"]), "01618813744")
        P = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        for i in ("osm-node-1533578890", "ww-55475981", "hl-dens-the-elms", "osm-way-556071354", "ww-57951889"): self.assertIn("| `%s` " % i, P)
        C = J("overrides/shelters_contacts.json")
        for i in ("hl-dens-the-elms", "osm-way-556071354"): self.assertNotIn("phone_fix", C[i])
        self.assertEqual(C["osm-way-169564851"]["phone_fix"], "01904 553626")
        for i in [k for k in d if k.startswith("milton-keynes/")]: self.assertNotIn("0300 303 4933", d[i].get("notice") or "", i)
    def test_address_name_website(self):
        d = items()
        self.assertIn("RH13 9BT", d["horsham-district/hub-on-the-move-southwater"]["address"])
        self.assertIn("SP9 7EA", d["salisbury/tidworth"]["address"])
        self.assertEqual(d["south-gwynedd/penrynduedraeth"]["name"], "Penrhyndeudraeth")
        self.assertEqual(d["headley-down"]["website"], "https://www.hdcc.uk/copy-of-about-us")
        for i in ("cgcc", "crieff", "rushcliffe", "the-shack-food-project"): self.assertIn(i, d); self.assertFalse(d[i]["website"])
        W = J("overrides/foodbank_websites.json"); self.assertEqual(W["crieff"]["url"], "")
        self.assertIn("foodbank_websites.json", open(os.path.join(ROOT, "scripts", "build.py")).read())
    def test_aberdeen_north_london_corby_unchanged_address(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i in ("salvation-army/aberdeen-citadel", "salvation-army/north-london", "salvation-army/corby", "salvation-army/bideford"):
            self.assertFalse([l for l in L if l["id"] == i and l["kind"] == "address"], i); self.assertTrue(d[i].get("notice"), i)
    def test_every_change_has_undo(self):
        for l in J("logs/listings_batch_28oct.json")["changes"]: self.assertIn("undo", l); self.assertIn("old", l)
if __name__ == "__main__": unittest.main()
class TimesRecheck0620(unittest.TestCase):
    WANT = {"medway/the-net-community-cafe": {"thu": [["09:30", "12:00"]]},
            "medway/twydall-foodbank-centre-coffee-shop": {"tue": [["12:30", "14:30"]], "fri": [["10:30", "12:30"]]},
            "lambeth-croydon/croydon": {"thu": [["11:00", "13:00"]]},
            "rickmansworth/mill-end": {"tue": [["13:45", "16:00"]], "fri": [["10:00", "12:00"]]},
            "rickmansworth/st-lawrence-abbots-langley": {"tue": [["10:00", "13:00"]], "thu": [["09:00", "11:00"]], "fri": [["10:00", "13:00"]]}}
    def test_times_and_undo(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i, w in self.WANT.items():
            self.assertEqual(d[i]["opening_times"]["structured"], w, i)
            self.assertTrue(any(l["id"] == i and l["kind"] == "hours" and "undo" in l for l in L), i)
        self.assertIn("Appointment only", d["lambeth-croydon/croydon"]["notice"])
        # A/L Citizens Advice at the same postcode keeps its own hours
        self.assertEqual(d["rickmansworth/abbots-langley"]["opening_times"]["structured"]["mon"], [["10:00", "14:00"]])
    def test_wendover_held(self):
        self.assertFalse(any(l["id"] == "chiltern/wendover" and "06:20" in l.get("note", "") for l in J("logs/listings_batch_28oct.json")["changes"]))
        self.assertIn("HELD `chiltern/wendover`", open(os.path.join(ROOT, "reports", "pending_dean.md")).read())
class OwnSiteAudit28Oct(unittest.TestCase):
    """Dean 28 Oct: every postcode, address, phone and time must be on the organisation's own page (2 reads)."""
    POSTCODES = {"horsham-district/united-reform-church": "RH12 1PT", "salisbury/durrington-old-school": "SP4 8HP", "lambeth-croydon/streatham": "SW16 3NN", "wandsworth/roehampton-methodist-church": "SW15 4EB", "clevedon-district/portishead": "BS20 7DB", "rickmansworth/croxley-green-baptist-church": "WD3 3PF", "aylesbury/esquires-coffee-shop": "HP18 1AS", "colchester/highwoods": "CO4 9YN", "st-neots/st-marys-eaton-socon": "PE19 8EQ", "sparkhill/hall-green": "B28 8JQ", "sparkhill/st-johns-church": "B11 4RG", "sparkhill/balsall-heath": "B12 9LA"}
    def test_postcodes_from_own_address_line(self):
        d = items(); F = J("overrides/foodbank_address_fixes.json"); L = J("logs/listings_batch_28oct.json")["changes"]
        for i, pc in self.POSTCODES.items():
            self.assertEqual(d[i]["postcode"], pc, i); self.assertTrue(d[i]["address"].endswith(pc), i)
            self.assertEqual(F[i]["postcode"], pc, i); self.assertEqual((F[i]["lat"], F[i]["lng"]), (d[i]["lat"], d[i]["lng"]), i)
            self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "address" and l["new"] == pc and l["undo"]["set"]["postcode"] != pc], i)
        self.assertIn("1st Portishead Scout Hut, Station Road", d["clevedon-district/portishead"]["address"])
        for i, pc in (("horsham-district/hub-on-the-move-broadbridge-heath", "RH12 3XS"), ("stroud-district/wotton", "GL12 7AA")):
            self.assertEqual(d[i]["postcode"], pc, i); self.assertIn("HELD `%s`" % i, open(os.path.join(ROOT, "reports", "pending_dean.md")).read())
        self.assertEqual(d["thanet-food-link"]["postcode"], "CT9 2RD"); self.assertNotIn("thanet-food-link", F)
    def test_st_johns_sparkhill_times(self):
        self.assertEqual(items()["sparkhill/st-johns-church"]["opening_times"]["structured"], {"wed": [["10:30", "12:30"]]})
    def test_dead_links_replaced_link_only(self):
        d = items(); W = J("overrides/foodbank_websites.json")
        for i, u, n in (("crookston-community-group", "https://ccg.scot/locations", "01418824333"), ("waterlooville", "https://www.wecockchurch.org.uk/contact/", "02392255288"),
                        ("north-guildford", "https://www.guildfordfoodbank.org/", "07583025435"), ("glasgow-vineyard-storehouse", "https://dwellingplaceglasgow.org/contact-us/", "01413346746"),
                        ("rhayader", "https://www.thearchesrhayader.co.uk/contact/", "01597810921")):
            self.assertEqual(d[i]["website"], u, i); self.assertEqual(W[i]["url"], u, i); self.assertEqual(re.sub(r"\D", "", d[i]["phone"]), n, i)
    def test_known_times_never_blanked(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i in ["colchester", "corfe-mullen", "walk-inn", "the-community-cupboard", "stretton", "north-lakes", "broxbourne", "redcar-area", "selby-centre", "salvation-army/ivybridge", "salvation-army/dorchester", "salvation-army/hastings-temple", "rickmansworth/maple-cross", "aylesbury/tabitha-foodbank", "salvation-army/bourne", "salvation-army/chester", "newark/tuxford", "fusion/calderdale", "north-ayrshire/st-johns-church"]:
            self.assertTrue((d[i].get("opening_times") or {}).get("structured"), i)
            self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "hours" and l["note"].startswith("reverted")], i)
    def test_unconfirmed_times_reverted(self):
        L = J("logs/listings_batch_28oct.json")["changes"]
        for i in ["hope-for-belper", "ross-community-larder", "shepshed", "newlands", "woodley"]: self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "hours" and l["note"].startswith("reverted")], i)
