"""Dean-approved centre fixes (26 Oct 2026). Every fact is on the food bank's own page or Give Food.
Overrides are what the 3x-daily refresh reapplies, so a later refresh cannot put the old pins back.
Sources are named in the override evidence fields and in the pull request."""
import os, sys, json, unittest, tempfile, shutil
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import classify, closure, own_locations, shelter_contacts
from times import normalise
J = lambda f: json.load(open(os.path.join(ROOT, "overrides", f)))
KY = "https://www.kirkcaldyfoodbankcharity.org.uk/get-food"
SE = "https://southend.foodbank.org.uk/about-us/locations"
GA = "https://galashielsfoodbank.wordpress.com/get-food/"
HE = "https://helensburghlomondfoodbank.org/"
CLOSED = ["southend/earls-hall", "southend/eastwood", "southend/leigh", "southend/leigh-road-baptist-church"]
VOUCHER = ["southend/hawkwell-hockley", "southend/belle-vue-baptist-church", "southend/westcliff", "southend/shoeburyness"]
WALK = ["kirkcaldy/park-road-centre", "kirkcaldy/linton-lane-centre", "kirkcaldy/new-volunteer-house"]

def fb(i, **k):
    base = {"type": "foodbank", "foodbank": i, "name": i, "address": "x", "postcode": "AA1 1AA", "lat": 0, "lng": 0, "phone": "", "website": ""}
    base.update(id=i, **k); return base
def loc(i, **k):
    base = {"type": "location", "foodbank": i.split("/")[0], "name": i, "address": "x", "postcode": "AA1 1AA", "lat": 1, "lng": 1, "phone": "", "website": ""}
    base.update(id=i, **k); return base

def drop_closed(items, root=ROOT):
    """Same ids scripts/closure.py removes from overrides/foodbank_closed.json. Does not write the log."""
    man = {k for k in json.load(open(os.path.join(root, "overrides", "foodbank_closed.json"))) if not str(k).startswith("_")}
    items[:] = [i for i in items if i["id"] not in man]
    return items
def refresh(items):
    """The part of scripts/build.py that reapplies these fixes after Give Food is downloaded."""
    drop_closed(items)
    own_locations.protect_times(items, ROOT)
    classify.classify(items, ROOT)
    notes, labels = J("foodbank_notices.json"), J("phone_labels.json")
    phones = {k: v for k, v in J("phones.json").items() if not str(k).startswith("_")}
    sites = {k: v for k, v in J("foodbank_websites.json").items() if not str(k).startswith("_") and isinstance(v, str) and v}
    emails = {k: v for k, v in J("foodbank_emails.json").items() if not str(k).startswith("_") and isinstance(v, str) and v}
    nophone = {k for k in J("foodbank_no_phone.json") if not str(k).startswith("_")}
    unknown = {k for k in J("foodbank_hours_unknown.json") if not str(k).startswith("_")}
    for i in items:
        n = notes.get(i["id"])
        if isinstance(n, dict) and n.get("notice"): i["notice"] = n["notice"]
        elif i["id"] in unknown: i.pop("notice", None)
        if i.get("phone") and isinstance(labels.get(i["id"]), str): i["phone_label"] = labels[i["id"]]
        # build.py overwrites a Give Food phone from phones.json, and fills an IFAN phone only when the directory has none
        if i["id"] in phones and (not i["id"].startswith("ifan-") or not i.get("phone")): i["phone"] = phones[i["id"]]
        if i["id"] in sites: i["website"] = sites[i["id"]]
        if i["id"] in nophone:
            i.pop("phone", None); i.pop("tel", None); i.pop("phone_checked", None); i.pop("phone_label", None)
        if i["id"] in unknown: i["opening_times"] = None
        if i["id"] in emails: i["email"] = emails[i["id"]]
    return items

KY_HTML = """
<p>Park Road Centre</p><p>2 Park Road, Kirkcaldy</p><p>KY1 3EL</p><p>Opening hours:</p>
<p>Mondays: 10am-3pm</p><p>Tuesdays: 10am-1pm</p><p>Wednesdays: 10am-1pm</p><p>Thursdays: 10am-3pm</p><p>Friday: Closed</p>
<p>Linton Lane Centre (cabin)</p><p>Linton Lane, Kirkcaldy</p><p>KY2 6LF</p><p>Opening hours:</p>
<p>Monday: 10am-12.30pm</p><p>Tuesday: 10am-12.30pm</p><p>Wednesday: Closed</p><p>Thursday: 10am-12.30pm</p><p>Friday: 10am-12.30pm</p>
<p>New Volunteer House</p><p>16 East Fergus Place,</p><p>Kirkcaldy KY1 1XT</p><p>Opening hours:</p>
<p>Monday: 10am-12.30pm</p><p>Tuesday: Closed</p><p>Wednesday: 10am-12.30pm</p><p>Thursday: Closed</p><p>Friday: 10am-12.30pm</p>
<p>Link Living</p><p>*</p><p>Agency referrals only</p><p>Westbridge Mill, Bridge Street, Kirkcaldy KY1 1TE</p><p>Opening hours:</p>
<p>Monday:10am-4pm</p><p>Tuesday:10am-4pm</p><p>Wednesday:10am-4pm</p><p>Thursday: 10am-4pm</p><p>Friday: 10am-4pm</p>
"""
SE_HTML = """
<p>Friendship House, 484 Southchurch Road, SS1 2QA is DONATIONS ONLY. You are unable get a voucher or collect food from this location.</p>
<p>There are 4 distribution centres.</p>
<p>Monday 5pm - 6.30pm Hawkwell Faith, Hope and Charity Shop, 40 Hedingham Place, SS4 1UP. (Please check for changes on bank holidays)</p>
<p>Tuesday 1pm - 3pm Belle Vue Baptist Church, Belle Vue Avenue, SS1 2QZ.</p>
<p>Wednesday 1pm - 3pm St Saviours Church, Kings Road, SS0 8LL.</p>
<p>Thursday 12.30pm - 2.30pm Shoeburyness and Thorpe Bay Baptist Church, 90 Thorpedene Gardens, SS3 9JD.</p>
"""

class Parse(unittest.TestCase):
    def test_kirkcaldy_page_is_three_walk_in_centres_plus_link_living(self):
        cs = {c["postcode"]: c for c in own_locations.parse_kirkcaldy(KY_HTML)}
        self.assertEqual(set(cs), {"KY1 3EL", "KY2 6LF", "KY1 1XT", "KY1 1TE"})
        self.assertEqual(cs["KY1 3EL"]["name"], "Park Road Centre")
        self.assertEqual(cs["KY1 3EL"]["address"], "2 Park Road, Kirkcaldy, KY1 3EL")
        self.assertEqual(cs["KY1 3EL"]["structured"]["mon"], [["10:00", "15:00"]])
        self.assertEqual(cs["KY1 3EL"]["structured"]["thu"], [["10:00", "15:00"]])
        self.assertNotIn("fri", cs["KY1 3EL"]["structured"])
        self.assertEqual(cs["KY1 1XT"]["structured"], {"mon": [["10:00", "12:30"]], "wed": [["10:00", "12:30"]], "fri": [["10:00", "12:30"]]})
        self.assertEqual(cs["KY2 6LF"]["structured"]["fri"], [["10:00", "12:30"]])
        self.assertNotIn("wed", cs["KY2 6LF"]["structured"])
    def test_southend_page_is_four_voucher_centres_not_friendship_house(self):
        cs = own_locations.parse_southend(SE_HTML)
        self.assertEqual([c["postcode"] for c in cs], ["SS4 1UP", "SS1 2QZ", "SS0 8LL", "SS3 9JD"])
        self.assertTrue(all("SS1 2QA" not in c["address"] for c in cs))
        self.assertEqual(cs[0]["structured"], {"mon": [["17:00", "18:30"]]})
        self.assertEqual(cs[1]["structured"], {"tue": [["13:00", "15:00"]]})
        self.assertEqual(cs[2]["structured"], {"wed": [["13:00", "15:00"]]})
        self.assertEqual(cs[3]["structured"], {"thu": [["12:30", "14:30"]]})
        self.assertEqual(cs[0]["name"], "Hawkwell Faith, Hope and Charity Shop")
        self.assertEqual(cs[1]["name"], "Belle Vue Baptist Church")

class Refresh(unittest.TestCase):
    def stale(self):
        return [
            fb("kirkcaldy", name="Kirkcaldy Foodbank", address="Viewforth Church Hall, Viewforth Terrace, Kirkcaldy, KY1 3BW", postcode="KY1 3BW", lat=56.13, lng=-3.13),
            loc("kirkcaldy/linton-lane-centre", foodbank="Kirkcaldy Foodbank", name="Linton Lane Centre", postcode="KY2 6LF", lat=56.12, lng=-3.18),
            loc("kirkcaldy/new-volunteer-house", foodbank="Kirkcaldy Foodbank", name="New Volunteer House", postcode="KY1 1XT", lat=56.11, lng=-3.16),
            loc("kirkcaldy/link-living", foodbank="Kirkcaldy Foodbank", name="Link Living", postcode="KY1 1TE", lat=56.09, lng=-3.16),
            fb("southend", name="Southend Foodbank", address="Friendship House, 484 Southchurch Road, Southend-on-Sea, SS1 2QA", postcode="SS1 2QA", lat=51.54, lng=0.73,
               opening_times={"status": "TIMES_TEXT_ONLY", "raw": "Monday, Tuesday and Thursday between 9am - 2pm", "structured": None}),
            loc("southend/earls-hall", foodbank="Southend Foodbank", postcode="SS0 0RJ", lat=51.55, lng=0.69),
            loc("southend/eastwood", foodbank="Southend Foodbank", postcode="SS9 5PY", lat=51.56, lng=0.65),
            loc("southend/leigh", foodbank="Southend Foodbank", postcode="SS9 2AJ", lat=51.54, lng=0.65),
            loc("southend/leigh-road-baptist-church", foodbank="Southend Foodbank", postcode="SS9 1NN", lat=51.54, lng=0.66),
            loc("southend/hawkwell-hockley", foodbank="Southend Foodbank", name="Hawkwell & Hockley", postcode="SS4 1UP", lat=51.59, lng=0.69),
            loc("southend/belle-vue-baptist-church", foodbank="Southend Foodbank", postcode="SS1 2QZ", lat=51.54, lng=0.72),
            loc("southend/westcliff", foodbank="Southend Foodbank", postcode="SS0 8LL", lat=51.54, lng=0.68),
            loc("southend/shoeburyness", foodbank="Southend Foodbank", postcode="SS3 9JD", lat=51.53, lng=0.77),
            fb("kings-langley", name="Kings Langley Foodbank", address="All Saints Church, Church Lane, Kings Langley, WD4 8JS", postcode="WD4 8JS", lat=51.71, lng=-0.44),
            loc("kings-langley/apsley", foodbank="Kings Langley Foodbank", name="Apsley", address="St Mary's Church, London Road, Apsley, Hemel Hempstead, HP3 9ST", postcode="HP3 9ST", lat=51.73, lng=-0.46),
            loc("kings-langley/bennetts-end", foodbank="Kings Langley Foodbank", name="Bennetts End", address="Church Hall, St Benedict's Church, Peascroft Road, Hemel Hempstead, HP3 8EP", postcode="HP3 8EP", lat=51.74, lng=-0.44),
            fb("galashiels-and-area", name="Galashiels and Area Foodbank", address="St Peter's Church, 1 Parsonage Road, Galashiels, TD1 3HS", postcode="TD1 3HS", lat=55.61, lng=-2.80),
            loc("galashiels-and-area/focus-centre", foodbank="Galashiels and Area Foodbank", postcode="TD1 1DQ", lat=55.61, lng=-2.81),
            fb("helensburgh-lomond", name="Helensburgh & Lomond Foodbank", address="Helensburgh Community Hub, 116 East Princes Street, Helensburgh, G84 7DQ", postcode="G84 7DQ", lat=56.00, lng=-4.72),
            loc("helensburgh-lomond/st-modans-church-community-centre", foodbank="Helensburgh & Lomond Foodbank", postcode="G84 0RF", lat=56.01, lng=-4.80),
        ]
    def test_fixes_present_and_survive_a_second_refresh(self):
        items = refresh(self.stale())
        self.check(items)
        again = refresh(json.loads(json.dumps(items)))  # a later refresh sees the corrected file and must not undo it
        self.check(again)
    def check(self, items):
        by = {i["id"]: i for i in items}
        self.assertTrue(all(k not in by for k in CLOSED))
        k = by["kirkcaldy"]
        self.assertEqual(k["label_en"], "Donations only")
        self.assertEqual({c["id"] for c in k["centres"]}, set(WALK))
        p = by["kirkcaldy/park-road-centre"]
        self.assertEqual((p["postcode"], p["address"]), ("KY1 3EL", "2 Park Road, Kirkcaldy, KY1 3EL"))
        self.assertEqual(p["opening_times"]["structured"]["mon"], [["10:00", "15:00"]])
        self.assertEqual(p["opening_times"]["source_url"], KY)
        self.assertTrue(p["notice"].startswith("Walk-in"))
        self.assertEqual(by["kirkcaldy/new-volunteer-house"]["opening_times"]["structured"]["wed"], [["10:00", "12:30"]])
        self.assertTrue(by["kirkcaldy/new-volunteer-house"]["notice"].startswith("Walk-in"))
        self.assertIn("Agency referrals only", by["kirkcaldy/link-living"]["notice"])
        self.assertEqual(by["kirkcaldy/link-living"]["opening_times"]["structured"]["mon"], [["10:00", "16:00"]])
        s = by["southend"]
        self.assertEqual(s["label_en"], "Donations only")
        self.assertIsNone(s.get("opening_times"))
        self.assertEqual({c["id"] for c in s["centres"]}, set(VOUCHER))
        self.assertNotIn("SS1 2QA", " ".join(c["address"] for c in s["centres"]))
        self.assertEqual(by["southend/hawkwell-hockley"]["opening_times"]["structured"], {"mon": [["17:00", "18:30"]]})
        self.assertEqual(by["southend/belle-vue-baptist-church"]["opening_times"]["structured"], {"tue": [["13:00", "15:00"]]})
        self.assertEqual(by["southend/westcliff"]["opening_times"]["structured"], {"wed": [["13:00", "15:00"]]})
        self.assertEqual(by["southend/shoeburyness"]["opening_times"]["structured"], {"thu": [["12:30", "14:30"]]})
        self.assertEqual(by["southend/hawkwell-hockley"]["opening_times"]["source_url"], SE)
        self.assertIn("bank holidays", by["southend/hawkwell-hockley"]["notice"])
        kl = by["kings-langley"]
        self.assertEqual(kl["label_en"], "Donations only")
        self.assertEqual({c["id"] for c in kl["centres"]}, {"kings-langley/apsley", "kings-langley/bennetts-end"})
        g = by["galashiels-and-area"]
        self.assertIsNone(g.get("label_en"))
        self.assertEqual(g["opening_times"]["structured"]["wed"], [["13:00", "14:45"]])
        self.assertEqual(g["opening_times"]["structured"]["thu"], [["17:00", "18:00"]])
        self.assertEqual(g["opening_times"]["source_url"], GA)
        self.assertIn("emergencies", g["notice"])
        self.assertIn("13:00–14:45", g["notice"])
        self.assertIn("not be turned away empty handed", g["notice"])
        h = by["helensburgh-lomond"]
        self.assertIsNone(h.get("label_en"))
        self.assertEqual(h["opening_times"]["structured"], {"mon": [["10:00", "12:00"]], "thu": [["15:00", "19:00"]]})
        self.assertEqual(h["opening_times"]["source_url"], HE)
        self.assertEqual(by["helensburgh-lomond/st-modans-church-community-centre"]["opening_times"]["structured"], {"wed": [["13:00", "15:00"]]})
        ours = set(WALK + VOUCHER + CLOSED + ["kirkcaldy", "southend", "kings-langley", "galashiels-and-area", "helensburgh-lomond", "kirkcaldy/link-living", "helensburgh-lomond/st-modans-church-community-centre"])
        for i in items:
            if i["id"] not in ours: continue
            ot = i.get("opening_times") or {}
            if ot.get("status") == "TIMES_FOUND" and isinstance(ot.get("structured"), dict):
                self.assertEqual(list(ot["structured"]), sorted(ot["structured"], key=lambda d: ["mon","tue","wed","thu","fri","sat","sun"].index(d)))
                for spans in ot["structured"].values():
                    for a, b in spans:
                        self.assertRegex(a, r"^\d{2}:\d{2}$"); self.assertRegex(b, r"^\d{2}:\d{2}$")
    def test_locations_refresh_drops_centres_missing_from_the_page(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/overrides")
        try:
            cfg = {"_comment": "t", "kirkcaldy": {"url": KY, "min_centres": 4, "format": "kirkcaldy_distribution"},
                   "southend": {"url": SE, "min_centres": 4, "format": "southend_locations"}}
            json.dump(cfg, open(d + "/overrides/own_location_pages.json", "w"))
            json.dump({"_comment": "snap"}, open(d + "/overrides/foodbank_own_pages.json", "w"))
            items = self.stale()
            pages = {KY: KY_HTML, SE: SE_HTML}
            geo = lambda pcs: {p: (56.1, -3.1) if p.startswith("KY") else (51.5, 0.7) for p in pcs}
            log = own_locations.refresh(items, d, fetcher=lambda u: pages[u], geo=geo)
            ids = {i["id"] for i in items}
            self.assertEqual(log["kirkcaldy"]["status"], "ok")
            self.assertEqual(log["southend"]["status"], "ok")
            self.assertTrue(set(CLOSED) <= set(log["southend"]["dropped_not_on_page"]))
            self.assertTrue(all(k not in ids for k in CLOSED))
            snap = json.load(open(d + "/overrides/foodbank_own_pages.json"))
            self.assertEqual(snap["kirkcaldy/park-road-centre"]["postcode"], "KY1 3EL")
            self.assertIn("kirkcaldy/linton-lane-centre", ids)
            self.assertIn("kirkcaldy/new-volunteer-house", ids)
        finally:
            shutil.rmtree(d)
    def test_protected_times_beat_a_scraped_overwrite(self):
        i = loc("helensburgh-lomond", type="foodbank", opening_times={"status": "TIMES_TEXT_ONLY", "raw": "Monday 10-12 | Thursday 3-7pm | Wednesday; 1-3pm", "structured": None})
        own_locations.protect_times([i], ROOT)
        self.assertEqual(i["opening_times"]["structured"]["thu"], [["15:00", "19:00"]])
        self.assertTrue(str(i["opening_times"]["reader"]).startswith("hand-reviewed"))
        scraped = dict(i["opening_times"], structured={"mon": [["09:00", "17:00"]]}, reader="robot")
        i["opening_times"] = scraped
        own_locations.protect_times([i], ROOT)  # the next refresh puts the hand-checked hours back
        self.assertEqual(i["opening_times"]["structured"], {"mon": [["10:00", "12:00"]], "thu": [["15:00", "19:00"]]})

class Published(unittest.TestCase):
    def test_published_food_banks(self):
        t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
        items = json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]
        Refresh().check(items)  # the published file already has every fix
        refresh(items)  # and a later refresh keeps them
        Refresh().check(items)
    def test_closure_file_removes_the_four_southend_pins(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/overrides"); os.makedirs(d + "/logs")
        try:
            shutil.copy(os.path.join(ROOT, "overrides", "foodbank_closed.json"), d + "/overrides/foodbank_closed.json")
            items = [loc(i, name=i) for i in CLOSED] + [loc("southend/westcliff", name="Westcliff")]
            gone = closure.apply(items, d, fetcher=lambda u: (u, ""), auto=False)
            self.assertEqual(set(gone), set(CLOSED))
            self.assertEqual([i["id"] for i in items], ["southend/westcliff"])
        finally:
            shutil.rmtree(d)
    def test_st_monicas_phone_labelled(self):
        raw = J("shelters_contacts.json")["sa-st-monica-s-house-lifehouse"]
        self.assertEqual(raw["phone_fix"], "023 9282 5673")
        self.assertEqual(raw["phone_label"], "Portsmouth Churches Housing Association")
        self.assertIn("homeless.org.uk/homeless-england/service/portsmouth-churches-ha-st-pauls-house-portsmouth", raw["phone_source"])
        item = {"id": "sa-st-monica-s-house-lifehouse", "phone": "023 9229 7877", "tel": "02392297877"}
        shelter_contacts.apply([item])
        self.assertEqual(item["phone"], "023 9282 5673")
        self.assertEqual(item["tel"], "02392825673")
        self.assertEqual(item["phone_label"], "Portsmouth Churches Housing Association")
        shelter_contacts.apply([item])  # a later shelters refresh does not put the other number back
        self.assertEqual((item["phone"], item["phone_label"]), ("023 9282 5673", "Portsmouth Churches Housing Association"))
        t = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
        d = json.loads(t[t.index("{"):t.rindex("}") + 1])
        live = next(i for i in d["items"] if i["id"] == "sa-st-monica-s-house-lifehouse")
        self.assertEqual(live["phone"], "023 9282 5673")
        self.assertEqual(live["phone_label"], "Portsmouth Churches Housing Association")
        self.assertIn("phone_label", open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read())
        self.assertIn("Number for ", open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read())
    def test_access_chips_match_the_next_refresh(self):
        """access.js is rebuilt from the voucher CSVs at the end of every refresh. These chips must already be what that rebuild writes."""
        import csv, glob, build_access
        d = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
        items = json.loads(d[d.index("{"):d.rindex("}") + 1])["items"]
        files = sorted(glob.glob(os.path.join(ROOT, "overrides", "access", "voucher_split_*.csv")), key=lambda f: (("pass2" in f) or ("final" in f), f))
        m = {}
        for f in files:
            for r in csv.DictReader(open(f, encoding="utf-8", newline="")): m[r["id"]] = build_access.classify(r)
        out = {i["id"]: m.get(i["id"], "unconfirmed") for i in items if i.get("kind") not in ("warehouse", "dropoff")}
        live = json.loads(open(os.path.join(ROOT, "access.js"), encoding="utf-8").read().split("=", 1)[1].strip().rstrip(";"))
        self.assertEqual(out["kirkcaldy/park-road-centre"], "walkin")
        self.assertEqual(out["kirkcaldy/linton-lane-centre"], "walkin")
        self.assertEqual(out["kirkcaldy/new-volunteer-house"], "walkin")
        self.assertEqual(out["kirkcaldy/link-living"], "voucher")
        self.assertNotIn("kirkcaldy", out)
        for i in CLOSED: self.assertNotIn(i, out)
        for i in VOUCHER: self.assertEqual(out[i], "voucher")
        self.assertNotIn("southend", out)
        self.assertNotIn("kings-langley", out)
        self.assertEqual(out["galashiels-and-area"], "walkin")
        self.assertEqual(out["helensburgh-lomond"], "walkin")
        for i in ("kirkcaldy/park-road-centre", "kirkcaldy/linton-lane-centre", "kirkcaldy/new-volunteer-house", "kirkcaldy/link-living", "galashiels-and-area", "helensburgh-lomond", *VOUCHER):
            self.assertEqual(live.get(i), out[i], i)

class SidleyShipshape(unittest.TestCase):
    """Dean 26 Oct 2026, 08:12 GMT.
    Sidley hours, address and phone are printed on Bexhill Foodbank's voucher page.
    Shipshape keeps the named website and the email printed on its contact page, and no phone.
    Unknown hours stay unknown: the card shows the approved line, not a Mon-Sun table."""
    SID = "bexhill/sidley"
    SHP = "ifan-b595a2208802ba38bef45d-0"
    PAGE = "https://bexhill.foodbank.org.uk/emergency-food/i-have-a-food-voucher"
    WEB = "https://www.shipshape.org.uk"
    EMAIL = "info@shipshape.org.uk"
    def published(self):
        t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
        return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]
    def test_approved_so_the_gate_keeps_them(self):
        import auto_rules, publish_gate
        ok = auto_rules.approved("foodbanks", ROOT)
        self.assertIn(self.SID, ok); self.assertIn(self.SHP, ok)
        self.assertEqual(J("phones.json")[self.SID], "01424 322541")
        self.assertNotIn(self.SHP, J("phones.json"))
        self.assertEqual(J("foodbank_websites.json")[self.SHP], self.WEB)
        self.assertEqual(J("foodbank_emails.json")[self.SHP], self.EMAIL)
        self.assertIn(self.SHP, J("foodbank_no_phone.json"))
        self.assertIn(self.SHP, J("foodbank_hours_unknown.json"))
        build = open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8").read()
        for name in ("foodbank_websites.json", "foodbank_emails.json", "foodbank_no_phone.json", "foodbank_hours_unknown.json"):
            self.assertIn(name, build)
        self.assertEqual(publish_gate.hold_reasons("foodbanks", {"id": self.SHP}, False, ok, False), [])
        held = publish_gate.hold_reasons("foodbanks", {"id": "not-approved"}, False, ok, False)
        self.assertTrue(any(x.startswith("new place") for x in held))
        self.assertIn("no verified phone", held)
    def test_published_and_a_refresh_keeps_them(self):
        items = self.published()
        self.check(items)
        # a later refresh sees Give Food's shorter Sidley address and mobile, and a Shipshape phone and day table
        by = {i["id"]: i for i in items}
        by[self.SID]["address"] = "Canada Way, Bexhill, Bexhill-on-Sea, TN39 4FL"
        by[self.SID]["phone"] = "07866046106"
        by[self.SID]["opening_times"] = None
        by[self.SHP]["website"] = "https://www.shipshape.website/"
        by[self.SHP]["phone"] = "0114 250 0222"
        by[self.SHP]["tel"] = "01142500222"
        by[self.SHP]["email"] = ""
        by[self.SHP]["notice"] = "Highfield Trinity Church, S2 4UR"
        by[self.SHP]["opening_times"] = {"status": "TIMES_FOUND", "structured": {"mon": [["09:30", "15:30"]], "tue": [["09:30", "15:30"]]}}
        refresh(items)
        self.check(items)
        by = {i["id"]: i for i in items}
        self.assertEqual(by[self.SID]["phone"], "01424 322541")
        self.assertNotIn("07866", by[self.SID]["phone"])
        self.assertFalse(by[self.SHP].get("phone"))
        self.assertFalse(by[self.SHP].get("tel"))
        self.assertEqual(by[self.SHP]["website"], self.WEB)
        self.assertEqual(by[self.SHP]["email"], self.EMAIL)
    def check(self, items):
        by = {i["id"]: i for i in items}
        self.assertEqual([i["id"] for i in items].count(self.SID), 1)
        self.assertEqual([i["id"] for i in items].count(self.SHP), 1)
        s = by[self.SID]
        self.assertEqual(s["postcode"], "TN39 4FL")
        self.assertIn("Canada Way (Off Buxton Drive)", s["address"])
        self.assertEqual(s["phone"], "01424 322541")
        self.assertEqual(s["opening_times"]["structured"], {"fri": [["10:00", "11:30"]]})
        self.assertEqual(s["opening_times"]["source_url"], self.PAGE)
        self.assertTrue(s["opening_times"].get("protected") or str(s["opening_times"].get("reader", "")).startswith("hand-reviewed"))
        self.assertNotIn("mon", s["opening_times"]["structured"])
        parent = by["bexhill"]
        self.assertIn(self.SID, {c["id"] for c in parent["centres"]})
        centre = next(c for c in parent["centres"] if c["id"] == self.SID)
        self.assertIn("Canada Way (Off Buxton Drive)", centre["address"])
        h = by[self.SHP]
        self.assertEqual(h["postcode"], "S11 8AE")
        self.assertEqual(h["name"], "Shipshape Health and Wellbeing")
        self.assertEqual((h["lat"], h["lng"]), (53.367068, -1.477234))
        self.assertEqual(h["website"], self.WEB)
        self.assertEqual(h["email"], self.EMAIL)
        self.assertFalse(h.get("phone"))
        self.assertFalse(h.get("tel"))
        self.assertIsNone(h.get("opening_times"))
        self.assertFalse(h.get("notice"))
        self.assertNotIn(self.SHP, J("foodbank_notices.json"))
        # TIMES_FOUND with a structured week is what draws Mon-Sun, missing days as Closed
        self.assertFalse(h.get("opening_times") and h["opening_times"].get("status") == "TIMES_FOUND")
    def test_a_second_pin_at_the_same_place_is_a_duplicate(self):
        import discover
        items = self.published()
        sidley = {"name": "Sidley food bank", "postcode": "TN39 4FL", "lat": 50.85445, "lng": 0.46894, "website": "https://bexhill.foodbank.org.uk"}
        ship = {"name": "Shipshape Health and Wellbeing", "postcode": "S11 8AE", "lat": 53.367068, "lng": -1.477234, "website": "https://www.shipshape.org.uk"}
        self.assertTrue(discover.is_dup(sidley, items))
        self.assertTrue(discover.is_dup(ship, items))
        new, dup = discover.dedupe([sidley, ship, dict(ship)], items)
        self.assertEqual(new, [])
        self.assertEqual(dup, 3)
    def test_unknown_hours_use_the_approved_line(self):
        page = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        badge = open(os.path.join(ROOT, "v3.js"), encoding="utf-8").read()
        self.assertIn("Times unknown – call before you go", badge)
        self.assertIn("Call for opening times", page)
        self.assertIn('href="mailto:${esc(i.email)}"', page)
        links = page.split('<div class="links">')[1].split("</div>")[0]
        self.assertNotIn("mailto:", links)
        self.assertIn("'email'", open(os.path.join(ROOT, "scripts", "compact.py"), encoding="utf-8").read())
        js = open(os.path.join(ROOT, "data.js"), encoding="utf-8").read()
        self.assertIn(self.EMAIL, js)
        self.assertNotIn("0114 250 0222", js)
        self.assertNotIn("shipshape.website", js)
    def test_access_chips(self):
        import csv, glob, build_access
        d = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
        items = json.loads(d[d.index("{"):d.rindex("}") + 1])["items"]
        files = sorted(glob.glob(os.path.join(ROOT, "overrides", "access", "voucher_split_*.csv")), key=lambda f: (("pass2" in f) or ("final" in f), f))
        m = {}
        for f in files:
            for r in csv.DictReader(open(f, encoding="utf-8", newline="")): m[r["id"]] = build_access.classify(r)
        out = {i["id"]: m.get(i["id"], "unconfirmed") for i in items if i.get("kind") not in ("warehouse", "dropoff")}
        live = json.loads(open(os.path.join(ROOT, "access.js"), encoding="utf-8").read().split("=", 1)[1].strip().rstrip(";"))
        self.assertEqual(out[self.SID], "voucher")
        self.assertEqual(out[self.SHP], "unconfirmed")
        self.assertEqual(live[self.SID], "voucher")
        self.assertEqual(live[self.SHP], "unconfirmed")

class Hours(unittest.TestCase):
    def test_normalise_leaves_hand_reviewed_table(self):
        ot = J("opening_times.json")["galashiels-and-area"]
        self.assertEqual(normalise(ot)["structured"]["wed"], [["13:00", "14:45"]])
        self.assertTrue(ot["protected"])
if __name__ == "__main__":
    unittest.main()
