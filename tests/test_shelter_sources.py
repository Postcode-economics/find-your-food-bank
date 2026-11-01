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
        far = "Call 0161 861 9806 (8am-8pm) for advice. " + ("Other ways to reach us. " * 4) + "Find us at 339 Wilbraham Road, M16 8GL."
        self.assertEqual(S.phone_near(far, "M16 8GL"), "0161 861 9806")
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

class SecondPass(unittest.TestCase):
    def test_stoll_without_emergency_beds_is_supported_housing(self):
        self.assertTrue(S.veterans_supported_only("Stoll", "Supported housing for veterans at 446 Fulham Road, London SW6 1DT."))
        self.assertFalse(S.veterans_supported_only("Stoll", "Direct access emergency beds at 446 Fulham Road, London SW6 1DT."))
    def test_council_page_names_the_hostel_and_its_address(self):
        url = "https://www.coventry.gov.uk/hostels/river-hostel"
        html = "<html><body><h1>River Hostel</h1><p>River Hostel, 4 River Lane, Coventry CV1 4EZ. Direct access, open 24 hours. Phone 02477 714443.</p></body></html>"
        def fetch(u):
            if "coventry.gov.uk" in u and "sitemap" not in u:
                return page(html, url)
            return {"http": 404, "html": "", "final_url": u}
        hold = {"id": "hl-river", "name": "River Hostel", "website": "", "directory": "Homeless Link",
                "directory_url": "https://homeless.org.uk/x", "referral_postcode": "AB1 2CD", "category": "publishable"}
        bucket, rec = S.second_pass_one(hold, fetch, council_url=url, directory_text="Direct access hostel. Referral address AB1 2CD.")
        self.assertEqual(bucket, "verified", rec)
        self.assertEqual(rec["postcode"], "CV1 4EZ")
        self.assertNotEqual(S.norm_pc(rec["postcode"]), "AB12CD")
        self.assertIn("council page", rec["evidence"])
        self.assertFalse(any(k.startswith("council_") for k in rec))
    def test_refuge_is_not_fetched_on_the_second_pass(self):
        hold = {"id": "hl-refuge", "name": "Northside Women's Aid", "directory": "Homeless Link", "category": "publishable"}
        bucket, rec = S.second_pass_one(hold, lambda u: (_ for _ in ()).throw(AssertionError("fetched")),
                                        directory_text="Women's refuge for women at risk of domestic abuse")
        self.assertEqual(bucket, "excluded")
        self.assertNotIn("phone", rec)
    def test_search_page_does_not_pin_the_office_or_a_job_address(self):
        html = ("<html><title>You searched for YMCA Norwich Central</title><body>"
                "<h1>Search results for YMCA Norwich Central</h1><p>No pages matched.</p>"
                "<p>Send a CV to the HR / Payroll Officer, 35-37 Exchange Street, Norwich, Norfolk, NR2 1DP.</p>"
                "</body></html>")
        self.assertIsNone(S.best_building(S._text(html), "YMCA Norwich Central", "https://ymca.example/?s=YMCA+Norwich+Central"))
        self.assertFalse(S._place_url("https://ymca.example/?s=YMCA+Norwich+Central"))
        self.assertFalse(S._place_url("https://ymca.example/blog/hatfield-youth-club/"))
        self.assertFalse(S._place_url("https://www.birmingham.gov.uk/directory_record/462/yardley_cemetery_and_crematorium"))
        self.assertFalse(S._place_url("https://www.nottinghamshire.gov.uk/births-deaths-marriages-and-civil-partnerships/register-offices-and-fees/mansfield"))
        place = ("<html><body><h1>Norwich Central</h1><p>Where we are Norwich Central, 10 Winalls Yard, Norwich NR1 3GX. "
                 "Direct access hostel, open 24 hours.</p></body></html>")
        hit = S.best_building(S._text(place), "YMCA Norwich Central", "https://ymca.example/accommodation/norwich-central")
        self.assertEqual(S.norm_pc(hit[0]), "NR13GX")
        contact = ("<html><title>Contact Hostel</title><body><p>Email enquiries@contacthostel.co.uk "
                   "Find us at 339 Wilbraham Road, M16 8GL.</p></body></html>")
        hit = S.best_building(S._text(contact), "Contact Hostel", "https://contacthostel.co.uk/")
        self.assertEqual(S.norm_pc(hit[0]), "M168GL")
        self.assertFalse(S._place_url("https://contacthostel.co.uk/?s=Contact+Hostel"))
    def test_shared_houses_without_emergency_beds_are_held(self):
        self.assertTrue(S.shared_housing_only("St Mungo's - Camden Shared Houses", "Supported housing at 8 Warner Street, London EC1R 5HA."))
        self.assertFalse(S.shared_housing_only("St Mungo's - Camden Shared Houses", "Direct access emergency beds at 8 Warner Street, London EC1R 5HA."))
        page = ("https://mungos.example/camden-shared",
                "Camden Shared Houses, 8 Warner Street, London EC1R 5HA. Supported housing. Referral via the council.")
        cand = {"id": "hl-shared", "name": "St Mungo's - Camden Shared Houses", "website": "https://mungos.example/",
                "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/x", "hint": "hostel",
                "directory_text": "Hostel. Referral only via the council.", "operator_pages": [page]}
        bucket, rec = S.assess(cand, lambda u: {"http": 404, "html": "", "final_url": u}, "2026-10-31", [])
        self.assertEqual(bucket, "held")
        self.assertEqual(rec["category"], "supported")
        self.assertNotIn("postcode", rec)

class ReferralHostel(unittest.TestCase):
    PAGE = ("https://river.example/hostel",
            "River Hostel is run by River Trust in Sheffield. The building address is not published. "
            "Referral only via Sheffield Housing Options. Call 0114 273 1234. Do not turn up without a referral.")
    def test_area_card_has_no_pin_and_ignores_a_directory_postcode(self):
        card = S.referral_area_card("River Hostel", [self.PAGE])
        self.assertEqual(card["card_type"], "referral_hostel")
        self.assertEqual(card["area"], "Sheffield")
        self.assertEqual(card["operator"], "River Trust")
        self.assertEqual(card["phone"], "0114 273 1234")
        self.assertIn("Housing Options", card["referral_route"])
        self.assertEqual(card["postcode"], "")
        self.assertIsNone(card["lat"])
        self.assertTrue(card["no_pin"])
        self.assertIn("Referral needed, don't turn up without one", card["notice"])
        self.assertEqual(card["evidence_url"], self.PAGE[0])
        self.assertTrue(any(q["field"] == "phone" and "0114" in q["text"] for q in card["quotes"]))
    def test_direct_access_does_not_need_withheld_wording(self):
        page = ("https://river.example/river-hostel",
                "River Hostel is run by River Trust in Sheffield. Direct access overnight. Call 0114 273 1234.")
        card = S.referral_area_card("River Hostel", [page])
        self.assertEqual(card["card_type"], "referral_hostel")
        self.assertEqual(card["postcode"], "")
        self.assertIn("Direct access", card["referral_route"])
        self.assertEqual(card["notice"], "Call before you go")
        self.assertTrue(card["quotes"])
    def test_supported_housing_and_out_of_date_seasonal_are_not_cards(self):
        supported = ("https://river.example/house",
                     "River House is run by River Trust in Sheffield. Supported housing for six months. Referral via the council. Call 0114 273 1234.")
        self.assertIsNone(S.referral_area_card("River House", [supported]))
        winter = ("https://winter.example/shelter",
                  "Old Market Winter Night Shelter is run by Night Trust in Bristol. Referral via the council. Call 0117 111 2222. Opens each winter.")
        self.assertIsNone(S.referral_area_card("Old Market Winter Night Shelter", [winter]))
    def test_a_building_postcode_is_not_an_area_card(self):
        page = ("https://river.example/hostel", self.PAGE[1] + " Where we are River Hostel, 4 River Lane, Sheffield S1 2AB.")
        self.assertIsNone(S.referral_area_card("River Hostel", [page]))
    def test_a_directory_listing_alone_is_not_an_area_card(self):
        fields = S.hl_directory_fields(
            {"name": "River Trust - River Hostel", "website": "https://river.example/hostel",
             "directory_url": "https://homeless.org.uk/homeless-england/service/river-hostel/"},
            {"directory_text": "0114 273 1234 River Hostel in Sheffield. Referral via Sheffield Housing Options. Email stay@river.example.",
             "referral_procedure": "Referral via Sheffield Housing Options. Email stay@river.example.",
             "referral_address": "", "directory_url": "https://homeless.org.uk/homeless-england/service/river-hostel/"},
            "2026-10-31")
        self.assertIsNone(S.directory_area_card("River Trust - River Hostel", fields, []))
        quiet = [("https://river.example/", "River Trust runs several projects. " * 20)]
        self.assertIsNone(S.directory_area_card("River Trust - River Hostel", fields, quiet))
        confirm = ("https://river.example/hostel",
                   "River Hostel is open now in Sheffield and is run by River Trust. Referral via Sheffield Housing Options. Call 0114 273 1234. " * 2)
        card = S.directory_area_card("River Trust - River Hostel", fields, [confirm])
        self.assertEqual(card["evidence_level"], "operator")
        self.assertEqual(card["evidence_url"], confirm[0])
        self.assertEqual(card["postcode"], "")
        self.assertIsNone(card["lat"])
        self.assertEqual(card["town"], "Sheffield")
        self.assertEqual(card["phone"], "0114 273 1234")
        self.assertNotIn("@", card["referral_route"])
        self.assertNotIn("stay@river.example", card["referral_route"])
        clash = [("https://river.example/river-hostel",
                  "River Hostel in Sheffield. Call 0114 999 8888 for the hostel. Referral via housing options. " * 5)]
        self.assertIsNone(S.directory_area_card("River Trust - River Hostel", fields, clash))
        refuge = dict(fields, text="Women's refuge. " + fields["text"])
        self.assertIsNone(S.directory_area_card("Northside Women's Aid", refuge, [confirm]))
    def test_council_blocks_second_stage_and_tenancies_are_not_cards_and_an_exclusion_is_one_id(self):
        family = ("https://family.example/",
                  "Belvidere Family Centre is where the council places homeless families. Referral via housing options. Call 0800 731 6844.")
        self.assertIsNone(S.referral_area_card("Belvidere Family Centre", [family]))
        second = ("https://squared.example/mixed",
                  "Squared mixed hostel is second-stage move-on housing in Luton, run by Squared. Referral via the council. Call 01582 749011.")
        self.assertIsNone(S.referral_area_card("Squared mixed hostel", [second]))
        tenancy = ("https://nile.example/",
                   "Nile Road is run by Two Saints in Portsmouth. It is tenancy-based supported housing. Referral via the council. Call 023 9283 4989.")
        self.assertIsNone(S.referral_area_card("Nile Road", [tenancy]))
        shared = ("https://river.example/hostel",
                  "Northcott House is temporary accommodation the council places people into. "
                  + self.PAGE[1])
        self.assertIsNotNone(S.referral_area_card("River Hostel", [shared]))
        self.assertIsNone(S.referral_area_card("Northcott House", [shared]))
        blocked = S.excluded_shelter_ids()
        self.assertIn("hl-salvation-army-william-booth-house-hull", blocked)
        self.assertNotIn("hl-st-mungos-longhills", blocked)
        cleaned = S.strip_emails("Email stay@river.example then call the council.")
        self.assertNotIn("@", cleaned)
        self.assertIn("call the council", cleaned)
    def test_a_refuge_is_not_an_area_card(self):
        page = ("https://x.example/", "Northside Women's Aid is run by Women's Aid in Belfast. Referral only via the council. Call 028 9066 6049. Address is not published.")
        self.assertIsNone(S.referral_area_card("Northside Women's Aid", [page]))
    def test_area_page_card_and_not_a_map_pin(self):
        import build_seo
        html = build_seo.card_sh({"name": "River Hostel", "card_type": "referral_hostel", "area": "Sheffield",
                                   "phone": "0114 273 1234", "referral_route": "Sheffield Housing Options", "postcode": "AB1 2CD"})
        self.assertIn("Referral hostel", html)
        self.assertIn("don&#x27;t turn up without one", html)
        self.assertNotIn("AB1 2CD", html)
        self.assertFalse(build_seo.shelter_public({"card_type": "referral_hostel", "postcode": "AB1 2CD", "name": "River Hostel"}))
        src = open(os.path.join(S.ROOT, "layers.js"), encoding="utf-8").read()
        self.assertIn("card_type==='referral_hostel'", src)
        self.assertIn("card_type!=='referral_hostel'", src)
        clean = {"name": "River Hostel", "card_type": "referral_hostel", "no_pin": True, "area": "Sheffield",
                 "phone": "0114 273 1234", "referral_route": "Sheffield Housing Options", "postcode": ""}
        self.assertTrue(build_seo.shelter_public(clean))
        self.assertFalse(build_seo.shelter_public(dict(clean, postcode="AB1 2CD")))
        groups = build_seo.attach_referral_hostels({"Sheffield": [{"name": "Other", "postcode": "S1 2AB"}]}, [clean])
        self.assertEqual([i["name"] for i in groups["Sheffield"]], ["Other", "River Hostel"])
        self.assertNotIn("AB1 2CD", html)
        # the emergency / SWEP banner is not built from these cards
        for fn in ("scripts/swep.py", "scripts/alert.py"):
            body = open(os.path.join(S.ROOT, fn), encoding="utf-8").read()
            self.assertNotIn("referral_hostel", body)
            self.assertNotIn("area_cards", body)
    def test_area_cards_are_proposals_and_do_not_touch_phones(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "reports"))
        hold = {"id": "hl-river", "name": "River Hostel", "website": "https://river.example/hostel",
                "directory": "Homeless Link", "directory_url": "https://homeless.org.uk/x",
                "category": "publishable",
                "reason": "no building postcode on the operator page (directory postcode is a referral address only)"}
        refuge = {"id": "hl-refuge", "name": "Northside Women's Aid", "website": "https://refuge.example/",
                  "directory": "Homeless Link", "category": "publishable",
                  "reason": "no operator page to confirm a building address"}
        json.dump({"proposals": [], "held": [hold, refuge], "excluded": [], "counts": {"by_source": {}}, "about": ""},
                  open(os.path.join(d, "reports", "verified_new_places.json"), "w"))
        def fetch(u):
            if "refuge" in u: raise AssertionError("refuge fetched")
            if u.startswith("https://river.example/hostel"):
                return page("<html><body><p>%s</p></body></html>" % self.PAGE[1], self.PAGE[0])
            return {"http": 404, "html": "", "final_url": u}
        base = os.path.join(S.ROOT, "overrides", "phone_baseline.json")
        before = open(base, encoding="utf-8").read()
        counts = S.run_area_cards(root=d, fetcher=fetch, delay=0)
        self.assertEqual(counts["by_type"]["referral_hostel"], 1)
        self.assertEqual(counts["by_source"]["Homeless Link"]["proposed"], 1)
        saved = json.load(open(os.path.join(d, "reports", "verified_new_places.json")))
        card = saved["area_cards"][0]
        self.assertEqual(card["postcode"], "")
        self.assertIsNone(card["lat"])
        self.assertTrue(card["no_pin"])
        self.assertNotIn("referral_postcode", card)
        self.assertFalse(any(k.startswith("council_") for k in card))
        self.assertEqual(saved["proposals"], [])
        self.assertEqual(open(base, encoding="utf-8").read(), before)
        rules = json.load(open(os.path.join(S.ROOT, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
        self.assertTrue(rules["referral_hostel_auto_add"]["on"])

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

class HandCheck(unittest.TestCase):
    """31 Oct 2026 evening hand check. Published referral lines are the short ones, and only those cards."""
    LINES = {
        "man-contact-hostel": "Call the hostel on 0161 861 9806 (8am–8pm) to ask about a referral.",
        "man-one-ymca-bishops-stortford": "Ages 16–30: refer yourself or ask any agency to refer you on 01279 838 068.",
        "man-roundabout-hostel": "Call 0114 258 9829",
        "hl-dawn-centre-temporary-accommodation-project": "Single adults and couples with no children who have a Leicester connection: call 0116 221 2770 or Leicester Housing Options.",
        "hl-st-mungos-longhills": "Bristol connection needed: ask Bristol Council's homelessness team (0117 352 6800) or St Mungo's outreach (0117 407 0330) to refer you.",
        "hl-stonepillow-bognor-hostel": "Go to a Stonepillow day centre in Bognor Regis or Chichester for an assessment and referral.",
        "hl-paradigm-housing-group-lea-bridge-house-hostel": "Ask Waltham Forest Council or your outreach worker to apply for you. You'll need photo ID and proof of income.",
        "hl-connection-support-fishermead-hostel": "Ask Milton Keynes Council's housing team to refer you through the Supported Housing Panel.",
        "ss-63bf328f843d85a21d7bbdce": "Call New Start on 0151 708 7103 or ask your support worker to refer you.",
    }
    OFF = [
        "hl-salvation-army-william-booth-house-hull", "hl-nacro-nottingham-young-persons-accommodation",
        "hl-london-borough-of-southwark-northcott-house", "ss-6311880e295b30de42434135",
        "hl-bromford-hayward-road-hostel", "hl-city-of-york-council-homelessness-housing-schemes",
        "hl-two-saints-nile-road", "hl-solo-housing-the-old-post-office-maltings", "hl-squared-mixed-hostel",
        "hl-bournemouth-churches-ha-st-pauls-hostel", "ss-63a44ec1b00aca305c753133",
        "hl-renewal-programme-barking-road-hostel", "hl-look-ahead-slough-hostel",
        "hl-shp-arlington-road", "hl-shp-ashley-road", "hl-shp-king-georges-hostel",
        "hl-st-mungos-ealing-accommodation-services", "hl-st-mungos-endell-street",
        "hl-transform-housing-and-support-hersham-road-hostel", "hl-adullam-homes-ha-bury-aben-phase-3",
        "hl-turning-lives-around-seacole-scheme", "hl-the-salvation-army-fishermead-hostel",
        "hl-squared-hostel-for-expected-mothers", "hl-squared-mother-and-baby-hostel",
        "hl-squared-luton-hostels",  # 1 Nov: phone not on own page
    ]

    def test_published_cards_match_the_hand_check(self):
        raw = open(os.path.join(S.ROOT, "shelters.js"), encoding="utf-8").read()
        data = json.loads(raw.split("=", 1)[1].strip().rstrip(";"))
        by = {i["id"]: i for i in data["items"]}
        for iid, line in self.LINES.items():
            self.assertIn(iid, by, iid)
            item = by[iid]
            self.assertEqual(item.get("referral") or item.get("referral_route"), line)
            if item.get("card_type") == "referral_hostel":
                self.assertEqual(item.get("referral_route"), line)
                self.assertNotIn("@", line)
                self.assertEqual(item.get("postcode") or "", "")
                self.assertTrue(item.get("no_pin"))
        self.assertEqual(by["ss-63bf328f843d85a21d7bbdce"]["name"], "New Start Harm Reduction (women)")
        self.assertEqual(by["ss-63bf328f843d85a21d7bbdce"]["groups"], ["Women"])
        self.assertNotIn("/test", by["ss-63bf328f843d85a21d7bbdce"].get("website") or "")
        self.assertEqual(by["hl-connection-support-fishermead-hostel"]["groups"], ["Women"])
        self.assertNotIn("Salvation", by["hl-connection-support-fishermead-hostel"]["name"])
        refs = [i for i in data["items"] if i.get("card_type") == "referral_hostel"]
        self.assertEqual(sorted(i["id"] for i in refs), sorted(i for i in self.LINES if i.startswith(("hl-", "ss-"))))
        for iid in self.OFF:
            self.assertNotIn(iid, by)
        held = open(os.path.join(S.ROOT, "reports", "pending_dean.md"), encoding="utf-8").read()
        for iid in ("hl-bournemouth-churches-ha-st-pauls-hostel", "ss-63a44ec1b00aca305c753133", "hl-turning-lives-around-seacole-scheme"):
            self.assertIn(iid, held)
        self.assertIn("phone unconfirmed", held)
        self.assertIn("id/name mismatch", held)


if __name__ == "__main__":
    unittest.main()
