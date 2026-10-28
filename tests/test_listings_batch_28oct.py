"""Listings batch #239 (28 Oct 2026): proven own-page fixes, labels, and Dean-approved removals. Undo log: logs/listings_batch_28oct.json."""
import hashlib, json, os, re, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
def J(p): return json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
# Rejected private mobiles, withheld (private): only their SHA-256 is kept, so the digits are never written here.
PRIVATE = {"63030b5b6e85b1afd14b06b1b94866550b716b59fdbacf3e567844dbe308c997": "St Francis Ingleby Barwick vicar's mobile (ww-57951889)",
           "53a587188e81b35d3fc8389fe0ac3887ed42e3c0c5f9538f462ff63c5b8c7ab9": "Lambourn Lunch Club volunteer's mobile (ww-65437319)"}
def private_in(text, private=PRIVATE):
    """Labels of the private numbers found in text, however the digits are spaced or prefixed."""
    found = set()
    for m in re.finditer(r"(?:\+44|0)(?:[\s()-]{0,2}\d){9,11}", text):
        d = re.sub(r"\D", "", m.group(0)); d = "0" + d[2:].lstrip("0") if d.startswith("44") else d
        for n in {d, d[:11]}:
            h = hashlib.sha256(n.encode()).hexdigest()
            if h in private: found.add(private[h])
    return found
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
        # Dean 28 Oct 07:02: own-site confirmed phones are applied (verify_own_page.py AUTO_APPLY), each with its source URL and an undo.
        exp = {"scunthorpe/epworth-baptist-church": ("01427875839", "03001028061"), "aberdeen-south": ("07360162919", "01224569750"),
               "3food4u": ("01992842642", "07973166940"), "st-monicas": ("02077989025", "02088869568"),
               "salvation-army/alton": ("0142084456", "01420541778"),
               "stroud-district/dursley": ("03001023254", "01453367077"), "rickmansworth/abbots-langley": ("03442451296", "07716856892"),
               "shepway/lydd": ("01797320345", "07913573403")}  # St Austell, 12 Apostles, Leominster: see Review28Oct
        L = J("logs/listings_batch_28oct.json")["changes"]
        B = J("overrides/phone_baseline.json")["listings"]; O = J("overrides/phones.json"); S = J("overrides/phone_sources.json")
        for i, (old, new) in exp.items():
            self.assertEqual(dg(d[i]["phone"]), new, i); self.assertEqual(dg(d[i]["tel"]), new, i); self.assertEqual(dg(B[i]["phone"]), new, i)
            self.assertEqual(dg(O[i]), new, i); self.assertTrue(S[i]["source"].startswith("http"), i); self.assertIn("AUTO_APPLY", S[i]["note"], i)
            self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "phone" and l["note"].startswith("applied") and l["source"] == S[i]["source"] and dg(l["undo"]["set"]["phone"]) == old], i)
        self.assertEqual(d["3food4u"]["phone_label"], "WhatsApp only")
        P = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        held = {"micah-liverpool": "01517027206", "kinmel-bay-church": "07841678889", "st-philips": "07396614430", "portsmouth/paulsgrove": "02392385047"}
        for i, cur in held.items():
            self.assertEqual(dg(d[i]["phone"]), cur, i); self.assertIn("| `%s` " % i, P)
            self.assertFalse([l for l in L if l["id"] == i and l["kind"] == "phone" and l["note"].startswith("applied")], i)
        self.assertFalse(d["andover/test-valley-borough-council-office"]["phone"])  # council switchboard removed, listing kept
        self.assertIn("andover/test-valley-borough-council-office", P)
        self.assertNotEqual(dg(d["salvation-army/andover"]["phone"]), "01264335242")  # charity shop line not applied
        for i in [k for k in d if k.startswith("milton-keynes/") and k != "milton-keynes"]:
            if (d[i].get("notice") or "").startswith("Food bank help line"): self.assertIn("0300 303 4933", d[i]["notice"], i)
        self.assertEqual(sum(1 for k in d if k.startswith("milton-keynes/") and "0300 303 4933" in (d[k].get("notice") or "")), 12)
    def test_layer_phones(self):
        d = items(); dg = lambda s: re.sub(r"\D", "", s or "")
        self.assertEqual(dg(d["whitby"]["phone"]), "01947469004"); self.assertEqual(dg(d["whitby"]["tel"]), "01947469004")
        self.assertEqual(J("overrides/phone_baseline.json")["listings"]["whitby"]["phone"], "01947469004")
        self.assertTrue([l for l in J("logs/listings_batch_28oct.json")["changes"] if l["id"] == "whitby" and l["kind"] == "phone" and dg(l["undo"]["set"]["phone"]) == "07789765696"])
        def layer(f):
            t = open(os.path.join(ROOT, f), encoding="utf-8").read(); return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
        S, W = layer("shelters.js"), layer("warmspaces.js")
        self.assertEqual(dg(S["osm-way-169564851"]["phone"]), "01904553626")  # James House, Dean approved
        self.assertFalse(W["ww-68618605"].get("phone"))  # Bruton council switchboard removal, Dean approved
        self.assertEqual(dg(S["osm-way-556071354"]["phone"]), "01414181955")  # Talbot Association own page
        self.assertFalse(private_in(json.dumps(W["ww-57951889"])))  # St Francis: vicar's personal mobile (directory page) is NOT on the listing
        self.assertEqual((dg(W["ww-57951889"]["phone"]), dg(W["ww-57951889"]["tel"])), ("07821153701", "07821153701"))  # undo value restored
        self.assertEqual(J("overrides/phone_baseline.json")["listings"]["ww-57951889"]["phone"], "07821 153701")
        self.assertTrue([l for l in J("logs/listings_batch_28oct.json")["changes"] if l["id"] == "ww-57951889" and l["kind"] == "phone" and l["note"].startswith("reverted (review FAILED") and l["new"] == "07821 153701"])
        self.assertEqual(dg(S["hl-dens-the-elms"]["phone"]), "01442800131")  # DENS's own contact page names this as The Elms' number
        # Peasholme 01904 551901 approved by Dean (#238); JNR8 0161 881 3744 approved by Dean (#238)
        self.assertEqual(dg(S["osm-node-1533578890"]["phone"]), "01904551901"); self.assertEqual(dg(S["osm-node-1533578890"]["tel"]), "01904551901")
        self.assertEqual(dg(J("overrides/phone_baseline.json")["listings"]["osm-node-1533578890"]["phone"]), "01904551901")
        self.assertEqual(J("overrides/shelters_contacts.json")["osm-node-1533578890"]["phone_fix"], "01904 551901")
        self.assertEqual(dg(W["ww-55475981"]["phone"]), "01618813744")
        P = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        self.assertNotIn("| `ww-55475981` ", P); self.assertNotIn("| `osm-node-1533578890` ", P)
        C = J("overrides/shelters_contacts.json")
        self.assertEqual((C["hl-dens-the-elms"]["phone_fix"], C["hl-dens-the-elms"]["phone_source"]), ("01442 800131", "https://www.dens.org.uk/contact/"))
        self.assertEqual(C["osm-way-556071354"]["phone_fix"], "0141 418 1955")
        self.assertEqual(C["osm-way-169564851"]["phone_fix"], "01904 553626")
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
REVERTED_TIMES = ["colchester", "corfe-mullen", "walk-inn", "the-community-cupboard", "stretton", "north-lakes", "broxbourne", "redcar-area", "salvation-army/ivybridge", "salvation-army/dorchester", "salvation-army/hastings-temple", "rickmansworth/maple-cross", "aylesbury/tabitha-foodbank", "salvation-army/bourne", "salvation-army/chester", "newark/tuxford", "fusion/calderdale", "north-ayrshire/st-johns-church", "hope-for-belper", "ross-community-larder", "shepshed", "newlands"]
def last_hours(L, i):
    return [l for l in L if l["id"] == i and l["kind"] == "hours"][-1]
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
    def test_unconfirmed_times_held(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i in ["hope-for-belper", "ross-community-larder", "shepshed", "newlands"]: self.assertTrue(last_hours(L, i)["note"].startswith("reverted"), i)
        self.assertEqual(d["woodley"]["opening_times"]["structured"], {k: [["10:00", "12:00"]] for k in ("mon", "tue", "wed", "thu", "fri")})
        self.assertTrue(last_hours(L, "woodley")["note"].startswith("applied"))
    def test_reverted_times_are_what_is_shown(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i in REVERTED_TIMES:
            e = last_hours(L, i); self.assertTrue(e["note"].startswith("reverted"), i)
            self.assertEqual(d[i].get("opening_times"), e["new"], i); self.assertNotEqual(e["undo"]["set"]["opening_times"], e["new"], i)
def _layer(f):
    t = open(os.path.join(ROOT, f), encoding="utf-8").read(); return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
class FaultScan28Oct(unittest.TestCase):
    """Fault scan 28 Oct: only verify_own_page.py AUTO_APPLY rows applied, each with source URL and undo."""
    def test_phones(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]; S = J("overrides/phone_sources.json")
        for i, n, old in (("quex-road", "02076241701", "02077989025"), ("wansbeck-valley/ymca", "01670943014", "01670857167")):  # Sunshine CC: reverted, see Review28Oct
            self.assertEqual(d[i]["phone"], n, i); self.assertEqual(J("overrides/phone_baseline.json")["listings"][i]["phone"], n, i)
            self.assertTrue(d[i]["phone_label"]); self.assertTrue(S[i]["source"].startswith("http"), i)
            self.assertTrue([l for l in L if l["id"] == i and l["kind"] == "phone" and l["new"] == n and l["undo"]["set"]["phone"] == old], i)
        self.assertEqual(d["highland/dingwall"]["phone"], "07884869020")  # REVIEW: held
    def test_times_and_address(self):
        d = items()
        self.assertEqual(d["harlow/the-harvey-centre"]["opening_times"]["structured"], {k: [["10:00", "14:00"]] for k in ("mon", "tue", "wed", "thu", "fri")})
        self.assertEqual(d["harlow/the-harvey-centre"]["postcode"], "CM20 1LS")  # held: own page gives two postcodes
        m = d["manchester-central"]; self.assertEqual((m["postcode"], m["address"]), ("M4 7JE", "Trinity Methodist Church, Butler St, Ancoats, Manchester, M4 7JE"))
        self.assertEqual(J("overrides/foodbank_address_fixes.json")["manchester-central"]["postcode"], "M4 7JE")
        self.assertIn("M4 7JE", J("overrides/district_cache.json"))
        self.assertEqual(d["salvation-army/faversham"]["postcode"], "ME13 7JL")  # held: ME13 7AW not valid on postcodes.io
        W = _layer("warmspaces.js"); K = {e["id"]: e for e in J("overrides/warmspaces_locked.json")["items"]}
        for i, h in (("ww-62981326", {"Mon": "12:30 - 15:00"}), ("ww-65437319", {"Thu": "12:00 - 13:30"})):
            self.assertEqual(W[i]["hours"], h, i); self.assertEqual(K[i]["set"]["hours"], h, i)
        self.assertEqual(W["ww-64623495"]["hours"]["Wed"], "09:00 - 12:00"); self.assertEqual(W["ww-65437319"]["phone"], "07564 984210")
    def test_duplicates_removed_with_exclusion_and_undo(self):
        d = items(); ex = {e["slug"]: e for e in J("overrides/foodbank_exclude.json")["foodbanks"]}; L = J("logs/listings_batch_28oct.json")["changes"]
        for gone, keep in (("salvation-army/tavistock", "tavistock"), ("salvation-army/risca", "risca"), ("salvation-army/ilfracombe", "northern-devon/ilfracombe"),
                           ("salvation-army/connahs-quay", "flintshire/connahs-quay"), ("salvation-army/goldthorpe", "barnsley/goldthorpe"), ("salvation-army/royston", "barnsley/royston"),
                           ("salvation-army/shildon", "county-durham/shildon"), ("salvation-army/bedford-congress-hall", "bedford/salvation-army-bedford"), ("salvation-army/penge", "bromley-borough/penge")):
            self.assertNotIn(gone, d); self.assertIn(keep, d); self.assertTrue(ex[gone]["exact"]); self.assertIn(keep, ex[gone]["reason"])
            e = [l for l in L if l["kind"] == "removed" and l["id"] == gone][0]; self.assertEqual(e["undo"]["set"]["listing"]["postcode"], d[keep]["postcode"])
        for i in ("salvation-army/crook", "county-durham/crook", "salvation-army/cottenham", "ely/cottenham", "salvation-army/clay-cross", "clay-cross"): self.assertIn(i, d)
    def test_warm_space_website_field(self):
        import sys; sys.path.insert(0, os.path.join(ROOT, "scripts")); import ws_website
        W = _layer("warmspaces.js")
        for i in ("ww-69005962", "ww-69068971", "ww-69208997", "ww-68990442"): self.assertFalse(W[i].get("website"), i)
        self.assertFalse([i for i, x in W.items() if x.get("website") and not ws_website.is_url(x["website"])])
        x = [{"id": "a", "website": "We do not have a website"}, {"id": "b", "website": "undefined"}, {"id": "c", "website": "www.example.org/x"}, {"id": "d", "website": "https://a.b/c?d=1"}]
        self.assertEqual([i for i, _ in ws_website.clean(x)], ["a", "b"]); self.assertEqual(x[2]["website"], "www.example.org/x")
        self.assertIn("ws_website.clean(items)", open(os.path.join(ROOT, "scripts", "build_warmspaces.py")).read())
class Review28Oct(unittest.TestCase):
    """Review of #239 (28 Oct 10:07): St Austell, Southborough, 12 Apostles, Leominster, and no rejected private mobile anywhere."""
    def setUp(self):
        self.d = items(); self.L = J("logs/listings_batch_28oct.json")["changes"]; self.B = J("overrides/phone_baseline.json")["listings"]
        self.O = J("overrides/phones.json"); self.S = J("overrides/phone_sources.json")
    dg = staticmethod(lambda s: re.sub(r"\D", "", s or ""))
    def last(self, i, field="phone"):
        return [l for l in self.L if l["id"] == i and l["kind"] == "phone" and l["field"] == field][-1]
    def shown(self, i, n):
        x = self.d[i]
        self.assertEqual((self.dg(x["phone"]), self.dg(x["tel"]), self.dg(self.B[i]["phone"]), self.dg(self.B[i]["tel"])), (n, n, n, n), i)
    def test_st_austell_corps_number_not_the_charity_shop(self):
        i = "salvation-army/st-austell"; self.shown(i, "07827192126")
        self.assertEqual((self.dg(self.O[i]), self.S[i]["source"]), ("07827192126", "https://www.salvationarmy.org.uk/st-austell"))
        self.assertIn("Phone: 07827192126", self.S[i]["note"]); self.assertIn("charity-shop manager", self.S[i]["note"])
        e = self.last(i); self.assertEqual((e["old"], e["new"], e["undo"]["set"]["phone"]), ("01726890174", "07827192126", "01726890174"))
    def test_southborough_back_to_the_hubs_own_line(self):
        i, w = "family-food-bank/sunshine-cc", "family-food-bank/west-borough-cc"
        self.shown(i, "03000417770"); self.shown(w, "03000419361")
        self.assertFalse(self.d[i].get("phone_label")); self.assertNotIn(i, J("overrides/phone_labels.json"))
        page = "https://www.familyfoodbank.org/maidstone-ffb.html"
        self.assertEqual((self.S[i]["source"], self.S[w]["source"]), (page, page))  # both hubs' numbers from the same own page
        self.assertIn("Tel: 03000 417770", self.S[i]["note"])
        e = self.last(i); self.assertTrue(e["note"].startswith("reverted")); self.assertEqual((e["new"], e["undo"]["set"]["phone"]), ("03000417770", "01233500477"))
        self.assertEqual(e["undo"]["set"]["phone_label"], "Food bank help line")
    def test_12_apostles_evidence_is_the_home_page(self):
        i = "12-apostles"; self.shown(i, "01707650147"); self.assertEqual(self.dg(self.O[i]), "01707650147")
        self.assertEqual(self.S[i]["source"], "https://www.12apostles.co.uk/"); self.assertIn("01707 650147", self.S[i]["note"])
        e = self.last(i, "phone_source"); self.assertEqual((e["new"], e["undo"]["set"]["phone_source"]), ("https://www.12apostles.co.uk/", "https://www.12apostles.co.uk/foodbank"))
    def test_leominster_held_for_dean(self):
        i = "leominster"; self.shown(i, "07715410575")  # main's number
        self.assertNotIn(i, self.O); self.assertNotIn(i, self.S)
        h = J("overrides/phone_holds.json")[i]; self.assertEqual(self.dg(h["phone"]), "07563000862"); self.assertIn("Dean", h["reason"])
        e = self.last(i); self.assertTrue(e["note"].startswith("reverted")); self.assertEqual((e["new"], e["undo"]["set"]["phone"]), ("07715410575", "07563000862"))
        self.assertIn("| `leominster` ", open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read())
        self.assertIn("HELD `leominster`", open(os.path.join(ROOT, "reports", "pending_dean.md"), encoding="utf-8").read())
    def test_private_mobiles_withheld_everywhere(self):
        demo = {"658163460ccdae4ea76abe5608181e9a9124542efc32c36cb1314fbe01b59d0e": "stand-in"}  # 07700 900461, Ofcom drama range: the check itself works
        for t in ("call 07700 900 461", "+44 7700 900461", "+44 (0)7700-900461", "tel:07700900461"): self.assertEqual(private_in(t, demo), {"stand-in"}, t)
        self.assertFalse(private_in("07700 900462", demo))
        files = ["data.full.js", "data.js", "warmspaces.js", "shelters.js", "PHONES-FOR-DEAN.md", "HANDOFF-239.md", "reports/pending_dean.md",
                 "logs/listings_batch_28oct.json", "export/warmspaces.csv", "export/warmspaces.json"]
        files += ["overrides/" + f for f in os.listdir(os.path.join(ROOT, "overrides")) if f.endswith(".json")]
        files += ["tests/" + f for f in os.listdir(os.path.join(ROOT, "tests")) if f.endswith(".py")]
        for f in files:
            self.assertFalse(private_in(open(os.path.join(ROOT, f), encoding="utf-8").read()), f)
        self.assertIn("withheld (private)", open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read())
        self.assertTrue([l for l in self.L if l["id"] == "ww-57951889" and l["old"] == "withheld (private)"])
