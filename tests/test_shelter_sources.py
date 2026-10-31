"""Hermetic checks for the shelter directory readers, classification, and evidence.
Directory postcodes are referral addresses. A proposal needs a building postcode on the operator page.
Women's refuges are never mapped. Fixtures are the page shapes; nothing here hits the network."""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import shelter_sources as S
import discover

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "shelter_sources")
def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f: return f.read()
def page(body, url): return {"http": 200, "final_url": url, "html": body, "sha256": "x"}

class Postcode(unittest.TestCase):
    def test_near_unit_is_the_same_place(self):
        self.assertTrue(S.postcodes_near("CV1 4EZ", "CV1 4EY"))
        self.assertTrue(S.postcodes_near("cv14ez", "CV1 4EZ"))
        self.assertFalse(S.postcodes_near("CV1 4EZ", "CV1 5EZ"))
        self.assertFalse(S.postcodes_near("CV1 4EZ", "AB1 2CD"))
    def test_same_place_needs_a_distinctive_name(self):
        self.assertTrue(S.same_place("Harnall Lifehouse", ["CV1 4EZ"], "Harnall Lifehouse", "CV1 4EY"))
        self.assertFalse(S.same_place("Harnall Lifehouse", ["CV1 4EZ"], "River Hostel", "CV1 4EY"))

class Classify(unittest.TestCase):
    def test_refuge_excluded_supported_held_hostel_publishable(self):
        self.assertEqual(S.classify("Northside Women's Aid", "Women's refuge for women at risk of domestic abuse"), "excluded")
        self.assertEqual(S.classify("Emmaus Bristol", "long-term supported housing"), "supported")
        self.assertEqual(S.classify("River Hostel", "direct access hostel"), "publishable")
        self.assertEqual(S.classify("Archer Drop In", "daytime drop-in, no beds"), "day_centre")
        self.assertEqual(S.classify("Some House", "supported housing for six months", "supported"), "supported")
        self.assertEqual(S.classify("Nightsafe House", "emergency hostel", "hostel"), "publishable")
    def test_accepting_domestic_abuse_survivors_is_not_a_refuge(self):
        self.assertNotEqual(S.classify("Annsgate Crisis", "Single women's homeless crisis accommodation service"), "excluded")
    def test_access_route_stands_in_for_opening_times(self):
        route = S.access_route("Open overnight. 24/7, referral via council. Bring ID.")
        self.assertIn("referral via council", route)
        self.assertTrue(S.referral_based(route))
        self.assertEqual(S.access_type_of(route), "referral_only")
        self.assertFalse(S.referral_based(S.access_route("Direct access from 8pm.")))
        self.assertFalse(S.referral_based(S.access_route("No referral needed.")))
        self.assertEqual(S.access_route("A room is offered within 12-24 hours."), "")
        self.assertEqual(S.access_type_of(S.access_route("We do not accept self-referrals.")), "")
        self.assertEqual(S.seasonal_reason("Old Market Winter Night Shelter", "Opens each winter."),
                         "seasonal night shelter: held until 2026-27 dates appear")
        self.assertEqual(S.seasonal_reason("Old Market Winter Night Shelter", "Open November 2026 to March 2027."), "")
    def test_footer_postcode_is_not_the_building(self):
        text = load("operator_place.html")
        hit = S.best_building(S._text(text), "River Hostel")
        self.assertEqual(S.norm_pc(hit[0]), "CV14EZ")
        self.assertEqual(S.phone_near(S._text(text), "CV1 4EZ"), "02477 714443")
        footer = "Alabare Homeless Charity privacy notice cookie sitemap GET IN TOUCH SP2 7UD"
        self.assertIsNone(S.best_building(footer, "Alabare Supported Housing South", "https://alabare.co.uk/"))
        many = "Chalvey is in Slough. YMCA Hayes UB3 4DQ. YMCA Ealing W5 2QB. YMCA Parsons Green SW6 4TQ."
        self.assertIsNone(S.best_building(many, "YMCA Slough Chalvey Hostel", "https://ymcastpaulsgroup.org/services/housing/supported-housing/"))

class Readers(unittest.TestCase):
    def test_homeless_link_pages_every_results_page(self):
        urls = {}
        base = "https://homeless.org.uk/homeless-england/"
        urls[base + "?service_types=accommodation&page=1"] = page(load("hl_page1.html"), base)
        urls[base + "?service_types=accommodation&page=2"] = page(load("hl_page2.html"), base)
        for slug, fn in (("river-hostel", "hl_river.html"), ("emmaus-bristol", "hl_emmaus.html"),
                         ("womens-aid-refuge", "hl_refuge.html"), ("winter-night-shelter", "hl_winter.html")):
            urls[base + "service/" + slug + "/"] = page(load(fn), base + "service/" + slug + "/")
        cands, st = S.read_homeless_link(lambda u: urls.get(u, {"http": 404, "html": ""}))
        self.assertEqual(st["status"], "ok")
        self.assertEqual(st["pages"], 2)
        self.assertEqual(st["found"], 4)
        by = {c["id"]: c for c in cands}
        river = by["hl-river-hostel"]
        self.assertEqual(river["referral_postcode"], "AB1 2CD")
        self.assertNotIn("postcode", river)
        self.assertEqual(river["website"], "https://river.example/hostel")
        self.assertIn("24/7, referral via council", river["directory_text"])
        self.assertEqual(S.classify(by["hl-womens-aid-refuge"]["name"], by["hl-womens-aid-refuge"]["directory_text"]), "excluded")
        self.assertEqual(S.classify(by["hl-emmaus-bristol"]["name"], by["hl-emmaus-bristol"]["directory_text"]), "supported")

    def test_street_support_overnight_and_dropin(self):
        accom = "https://www.streetsupport.net/api/services?category=accom&limit=100&page=1"
        drop = "https://www.streetsupport.net/api/services?category=dropin&limit=100&page=1"
        urls = {accom: page(load("street_support_accom.json"), accom), drop: page(load("street_support_dropin.json"), drop)}
        recs, st = S.read_street_support(lambda u: urls.get(u, {"http": 404, "html": ""}))
        self.assertEqual(st["status"], "ok")
        self.assertEqual(st["found"], 3)
        by = {r["name"]: r for r in recs}
        self.assertEqual(S.classify(by["Nightsafe House"]["name"], by["Nightsafe House"]["directory_text"], by["Nightsafe House"]["hint"]), "publishable")
        self.assertEqual(by["Nightsafe House"]["referral_postcode"], "BB1 1AA")
        self.assertEqual(by["Nightsafe House"]["website"], "https://nightsafe.example/house")
        self.assertEqual(S.classify(by["Woodward Court"]["name"], by["Woodward Court"]["directory_text"], "supported"), "supported")
        self.assertEqual(S.classify(by["Archer Drop In"]["name"], by["Archer Drop In"]["directory_text"], by["Archer Drop In"]["hint"]), "day_centre")

    def test_lifehouse_sitemap_skips_news(self):
        urls = {
            S.SA_SITEMAP: page(load("sa_sitemap.xml"), S.SA_SITEMAP),
            "https://www.salvationarmy.org.uk/sitemap.xml?page=1": page(load("sa_sitemap_page.xml"), "https://www.salvationarmy.org.uk/sitemap.xml?page=1"),
            S.SA_INDEX: page(load("sa_index.html"), S.SA_INDEX),
            "https://www.salvationarmy.org.uk/harnall-lifehouse": page(load("lifehouse.html"), "https://www.salvationarmy.org.uk/harnall-lifehouse"),
        }
        recs, st = S.read_lifehouses(lambda u: urls.get(u, {"http": 404, "html": "", "final_url": u}))
        self.assertEqual(st["found"], 1)
        self.assertEqual(st["stated_on_page"], 44)
        self.assertIn("44", st["note"])
        self.assertEqual(recs[0]["name"], "Harnall Lifehouse")
        self.assertEqual(S.classify(recs[0]["name"], recs[0]["directory_text"], "lifehouse"), "publishable")

    def test_nihe_excludes_refuges_and_keeps_no_address(self):
        rows, excluded = S.parse_nihe_text(load("nihe.txt"))
        names = {r["name"] for r in rows}
        self.assertIn("Centenary House Night Shelter", names)
        self.assertIn("Annsgate Crisis", names)
        self.assertNotIn("Northside Women's Aid", names)
        self.assertTrue(excluded)
        blob = json.dumps(excluded)
        self.assertNotIn("028 9066", blob)
        self.assertNotIn("AB", blob)
        miss = {"http": 403, "html": "", "final_url": S.NIHE_PAGE}
        text = page(load("nihe.txt"), S.NIHE_PDF)
        def fetch(u):
            if u == S.NIHE_PAGE: return miss
            if u == S.NIHE_PDF: return text
            return {"http": 404, "html": ""}
        recs, ex, st = S.read_nihe(fetch)
        self.assertEqual(st["status"], "ok")
        self.assertEqual(st["refuges_excluded"], 1)
        self.assertTrue(all(not r.get("referral_postcode") for r in recs))
        self.assertTrue(all(r["hint"] == "hostel" for r in recs))

class Evidence(unittest.TestCase):
    def fetcher(self):
        home = "https://river.example/hostel"
        sm = "https://river.example/sitemap.xml"
        place = "https://river.example/river-hostel"
        urls = {
            home: page(load("operator_home.html"), home),
            sm: page(load("operator_sitemap.xml"), sm),
            place: page(load("operator_place.html"), place),
        }
        return lambda u: urls.get(u, {"http": 404, "html": "", "final_url": u})

    def river(self):
        return {"id": "hl-river-hostel", "name": "River Hostel", "website": "https://river.example/hostel",
                "directory_text": "Direct access hostel. 24/7, referral via council.",
                "referral_address": "Housing Options, 1 Council House, AB1 2CD", "referral_postcode": "AB1 2CD",
                "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/homeless-england/service/river-hostel/",
                "hint": ""}

    def test_sitemap_follow_confirms_building_not_directory_postcode(self):
        bucket, rec = S.assess(self.river(), self.fetcher(), "2026-10-31", [])
        self.assertEqual(bucket, "verified", rec)
        self.assertEqual(rec["postcode"], "CV1 4EZ")
        self.assertNotEqual(S.norm_pc(rec["postcode"]), S.norm_pc(rec["referral_postcode"]))
        self.assertEqual(rec["referral_postcode"], "AB1 2CD")
        self.assertEqual(rec["phone"], "02477 714443")
        self.assertEqual(rec["phone_source"], "https://river.example/river-hostel")
        self.assertNotIn("0121", rec["phone"])
        self.assertEqual(rec["access_type"], "referral_only")
        self.assertIn("referral via council", rec["access"])
        self.assertEqual(rec["lat"], 52.415804)
        self.assertFalse(any(k.startswith("council") for k in rec))
        self.assertIn("operator page", rec["evidence"])

    def test_near_postcode_is_not_proposed_again(self):
        existing = [{"id": "sa-harnall", "name": "Harnall Lifehouse", "postcode": "CV1 4EY"}]
        cand = {"id": "sa-harnall-lifehouse", "name": "Harnall Lifehouse", "website": "https://www.salvationarmy.org.uk/harnall-lifehouse",
                "operator_pages": [("https://www.salvationarmy.org.uk/harnall-lifehouse", S._text(load("lifehouse.html")))],
                "directory_text": S._text(load("lifehouse.html")), "hint": "lifehouse",
                "directory": "Salvation Army Lifehouses", "directory_url": "https://www.salvationarmy.org.uk/harnall-lifehouse",
                "referral_postcode": ""}
        bucket, rec = S.assess(cand, lambda u: {"http": 404, "html": ""}, "2026-10-31", existing)
        self.assertEqual(bucket, "already")
        self.assertIsNone(rec)

    def test_no_operator_page_is_held_even_with_a_directory_postcode(self):
        cand = {"id": "ss-bb22", "name": "Nightsafe House", "website": "", "hint": "hostel",
                "directory_text": "Emergency hostel.", "referral_postcode": "BB1 1AA", "referral_address": "Housing Options, BB1 1AA",
                "directory": "Street Support", "directory_url": "https://www.streetsupport.net/find-help"}
        bucket, rec = S.assess(cand, lambda u: {"http": 404, "html": ""}, "2026-10-31", [])
        self.assertEqual(bucket, "held")
        self.assertNotIn("postcode", rec)
        self.assertIn("no operator page", rec["reason"])
        self.assertNotEqual(rec.get("postcode"), "BB1 1AA")

    def test_seasonal_and_refuge_and_supported_and_dropin(self):
        winter = {"id": "hl-winter", "name": "Old Market Winter Night Shelter", "website": "https://winter.example/",
                  "directory_text": "Winter night shelter. Opens each winter.", "hint": "", "referral_postcode": "BS1 1AA",
                  "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/x"}
        self.assertEqual(S.assess(winter, lambda u: {"http": 200, "html": "x", "final_url": u}, "2026-10-31", [])[0], "held")
        refuge = {"id": "hl-refuge", "name": "Northside Women's Aid", "directory_text": "Women's refuge for women at risk of domestic abuse. Phone 0800 111",
                  "referral_postcode": "AB9 9ZZ", "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/x"}
        bucket, rec = S.assess(refuge, lambda u: (_ for _ in ()).throw(AssertionError("refuge must not be fetched")), "2026-10-31", [])
        self.assertEqual(bucket, "excluded")
        self.assertNotIn("phone", rec)
        self.assertNotIn("AB9", json.dumps(rec))
        emmaus = {"id": "hl-emmaus", "name": "Emmaus Bristol", "directory_text": "long-term supported housing",
                  "referral_postcode": "ZZ1 1ZZ", "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/x"}
        bucket, rec = S.assess(emmaus, lambda u: {"http": 404, "html": ""}, "2026-10-31", [])
        self.assertEqual(bucket, "held")
        self.assertNotIn("postcode", rec)
        drop = {"id": "ss-cc", "name": "Archer Drop In", "hint": "dropin", "directory_text": "Daytime drop-in. No beds.",
                "referral_postcode": "S1 2AB", "directory": "Street Support", "directory_url": "https://www.streetsupport.net/find-help"}
        bucket, rec = S.assess(drop, lambda u: {"http": 404, "html": ""}, "2026-10-31", [])
        self.assertEqual(bucket, "day_centre")
        self.assertIn("held", rec["status"])

    def test_sitemap_follow_through_on_own_site_check(self):
        home = "https://river.example/hostel"
        sm = "https://river.example/sitemap.xml"
        place = "https://river.example/river-hostel"
        # own-site check looks for the candidate postcode, which here is the building postcode
        urls = {home: page("<html><body><h1>River Trust</h1><p>" + ("We run projects. " * 30) + "</p><a href='/river-hostel'>River Hostel</a></body></html>", home),
                sm: page(load("operator_sitemap.xml"), sm),
                place: page("<html><body><h1>River Hostel</h1><p>Where we are River Hostel, emergency accommodation, CV1 4EZ. " + ("Overnight hostel. " * 20) + "</p></body></html>", place)}
        r = discover.own_site_check({"name": "River Hostel", "postcode": "CV1 4EZ", "website": home}, "sh", lambda u: urls.get(u, {"http": 404, "html": "", "final_url": u}))
        self.assertEqual(r["result"], "add", r.get("reasons"))
        self.assertTrue(any("river-hostel" in u for u in r["pages"]))

class Report(unittest.TestCase):
    def test_cards_say_referral_needed_and_file_keeps_other_layers(self):
        import build_seo
        card = build_seo.card_sh(dict(name="River Hostel", address="4 River Lane", postcode="CV1 4EZ",
                                      tier="unverified", access_type="referral_only", referral="Referral only: via the council", hours=""))
        self.assertIn("Referral needed / check before you go", card)
        for fn in ("layers.js", "v3.js"):
            self.assertIn("Referral needed / check before you go", open(os.path.join(S.ROOT, fn), encoding="utf-8").read())
        # hours that only say 'By referral' keep the 25 Oct line as well
        self.assertIn("By referral – call before you go", open(os.path.join(S.ROOT, "v3.js"), encoding="utf-8").read())
        doc = {"generated": "2026-10-31", "proposals": [{"id": "hl-river-hostel", "layer": "shelters", "name": "River Hostel", "postcode": "CV1 4EZ"}],
               "held": [], "day_centre_candidates": [], "excluded": [], "counts": {}, "uncertain": []}
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "verified_new_places.json")
        json.dump({"proposals": [{"id": "ws-1", "layer": "warmspaces", "name": "Hall"}], "warm_note": "keep"}, open(path, "w"))
        S.write_report(path, doc)
        saved = json.load(open(path))
        ids = {p["id"] for p in saved["proposals"]}
        self.assertEqual(ids, {"hl-river-hostel", "ws-1"})
        self.assertEqual(saved["warm_note"], "keep")
        base = os.path.join(S.ROOT, "overrides", "phone_baseline.json")
        before = os.path.getmtime(base)
        S.build_report([("homeless_link", [], {"status": "ok", "found": 0}, [])], [], lambda u: {"http": 404, "html": ""}, "2026-10-31")
        self.assertEqual(os.path.getmtime(base), before)

if __name__ == "__main__":
    unittest.main()
