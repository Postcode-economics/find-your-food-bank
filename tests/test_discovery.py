import os, sys, unittest, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover, directories

def page(html, http=200, final=None, url="https://x.org/"):
    return {"http": http, "final_url": final or url, "html": html, "etag": "e", "last_modified": "", "sha256": hashlib.sha256(html.encode()).hexdigest()}
def fake(site_map):
    def f(u):
        for k, v in site_map.items():
            if u.rstrip("/") == k.rstrip("/"): return v
        return {"http": 404, "final_url": u, "html": ""}
    return f
FILL = " lorem ipsum" * 40
FB = "<html><body><h1>Riverside Food Bank</h1><p>We give emergency food parcels. Riverside Hall, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm.</p>" + FILL + "</body></html>"

class Dedupe(unittest.TestCase):
    E = [{"name": "Riverside Food Bank", "postcode": "AB1 2CD", "lat": 52.0, "lng": -1.0, "website": "https://riverside.org"}]
    def test_same_postcode_same_name(self):
        self.assertTrue(discover.is_dup({"name": "Riverside Foodbank", "postcode": "ab12cd", "lat": 52.1, "lng": -1.1}, self.E))
    def test_near_same_name(self):
        self.assertTrue(discover.is_dup({"name": "Riverside", "postcode": "", "lat": 52.001, "lng": -1.0}, self.E))
    def test_same_site_nearby(self):
        self.assertTrue(discover.is_dup({"name": "Other", "postcode": "", "lat": 52.01, "lng": -1.0, "website": "http://www.riverside.org/x"}, self.E))
    def test_new_place(self):
        self.assertFalse(discover.is_dup({"name": "Hilltop Pantry", "postcode": "ZZ9 9ZZ", "lat": 53.0, "lng": -2.0}, self.E))
    def test_dedupe_within_candidates(self):
        c = {"name": "Hilltop Pantry", "postcode": "ZZ9 9ZZ", "lat": 53.0, "lng": -2.0}
        new, dup = discover.dedupe([c, dict(c)], self.E); self.assertEqual((len(new), dup), (1, 1))

class OwnSite(unittest.TestCase):
    C = {"name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/"}
    def test_pass(self):
        self.assertEqual(discover.own_site_check(self.C, "fb", fake({"https://x.org/": page(FB)}))["result"], "add")
    def test_unreachable_flagged(self):
        r = discover.own_site_check(self.C, "fb", fake({"https://x.org/": page("", 503)}))
        self.assertEqual(r["result"], "flag"); self.assertIn("unreachable", r["reasons"][0])
    def test_redirect_elsewhere_flagged(self):
        r = discover.own_site_check(self.C, "fb", fake({"https://x.org/": page(FB, final="https://parked.example/")}))
        self.assertEqual(r["result"], "flag")
    def test_postcode_missing_flagged(self):
        r = discover.own_site_check(self.C, "fb", fake({"https://x.org/": page(FB.replace("AB1 2CD", ""))}))
        self.assertIn("postcode not on own site", r["reasons"])
    def test_closed_flagged(self):
        r = discover.own_site_check(self.C, "fb", fake({"https://x.org/": page(FB.replace("We give", "The food bank has now closed. We gave"))}))
        self.assertEqual(r["result"], "flag")
    def test_not_food_aid_flagged(self):
        r = discover.own_site_check(dict(self.C, name="Riverside Club"), "fb", fake({"https://x.org/": page("<p>Riverside Club bingo AB1 2CD</p>" + FILL)}))
        self.assertIn("own site does not show food aid", r["reasons"])
    def test_no_website_flagged(self):
        self.assertEqual(discover.own_site_check(dict(self.C, website=""), "fb")["result"], "flag")
    def test_shelter_referral_detected(self):
        h = "<p>Riverside Night Shelter AB1 2CD homeless beds. Access by referral only from the council.</p>" + FILL
        r = discover.own_site_check(dict(self.C, name="Riverside Night Shelter"), "sh", fake({"https://x.org/": page(h)}))
        self.assertEqual(r["result"], "add"); self.assertTrue(r.get("referral_only"))

def two_runs(it, kind, field, fetcher, root=None):
    """Dean 27 Oct (vault rule 33): a refresh times change applies only on the 2nd identical run; the 1st run must hold it."""
    import tempfile
    root = root or tempfile.mkdtemp(); ON = {"times_auto_apply": True}
    l1 = discover.cross_check_times([dict(x) for x in it], kind, field, fetcher, state_root=root, rules=ON, run_at="2026-10-27T03:00:00+00:00")
    return l1, discover.cross_check_times(it, kind, field, fetcher, state_root=root, rules=ON, run_at="2026-10-27T11:00:00+00:00")

class Times(unittest.TestCase):
    OT = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}}
    def items(self, ot=None, site="https://x.org/"):
        return [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": site, "opening_times": ot or dict(self.OT)}]
    def test_confirmed(self):
        it = self.items(); log = discover.cross_check_times(it, "fb", "opening_times", fake({"https://x.org/": page(FB)}))
        self.assertEqual(log["a"]["status"], "confirmed"); self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
    def test_changed_updated_via_times_py(self):
        it = self.items(); h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "Wednesday 9am - 11am")
        l1, log = two_runs(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))
        self.assertEqual(l1["a"]["status"], "held_for_dean")
        self.assertEqual(log["a"]["status"], "changed"); self.assertEqual(it[0]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})
        self.assertEqual(it[0]["opening_times"]["source_url"], "https://x.org/")
    def test_unreachable_never_carries_old_times(self):
        it = self.items(); log = discover.cross_check_times(it, "fb", "opening_times", fake({}))
        self.assertEqual(log["a"]["status"], "unreachable"); self.assertEqual(it[0]["times_status"], "unconfirmed")
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"]); self.assertNotIn("times_note", it[0]); self.assertEqual(it[0]["times_source"], "main database")
    def test_unconfirmed_withheld(self):
        it = self.items(); h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "see Facebook for times")
        log = discover.cross_check_times(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))
        self.assertEqual(log["a"]["status"], "unconfirmed"); self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"]); self.assertNotIn("times_note", it[0])
    def test_own_site_closed_marked_for_removal(self):
        it = self.items(); h = FB.replace("We give", "This food bank is permanently closed. We gave")
        log = discover.cross_check_times(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))
        self.assertEqual(log["a"]["status"], "closed"); self.assertTrue(it[0]["_own_site_closed"])
    def test_other_location_times_not_used(self):
        h = "<p>Riverside Food Bank food parcels. Hall A, ZZ1 1ZZ: Monday 9am - 10am. Hall B, YY1 1YY: Thursday 2pm - 4pm</p>" + FILL
        it = self.items(); it[0]["opening_times"] = None
        log = discover.cross_check_times(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))
        self.assertIsNone(it[0]["opening_times"])
    def test_shelter_hours_dict(self):
        it = [{"id": "s", "name": "Riverside Night Shelter", "postcode": "AB1 2CD", "website": "https://x.org/", "hours": {"Tue": "10:00 - 12:00"}}]
        h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "Tuesday 18:00 - 20:00")
        l1, _ = two_runs(it, "sh", "hours", fake({"https://x.org/": page(h)})); self.assertEqual(l1["s"]["status"], "held_for_dean")
        self.assertEqual(it[0]["hours"], {"Tue": "18:00 - 20:00"})

class Directories(unittest.TestCase):
    def test_ifan_parse(self):
        s = '{_id:"abc123",contact:[{_key:"k",_type:"website",value:"https://dfb.org.uk/"}],locations:[{_key:"l",_type:"location",authorities:[{_ref:"r",_type:"reference"}],coordinates:{_type:"geopoint",lat:50.34,lng:-3.59},postcode:"TQ6 9LJ"}],name:"Dartmouth \\u0026 District Food Bank"}'
        c = directories.parse_ifan(s)
        self.assertEqual(len(c), 1); self.assertEqual(c[0]["postcode"], "TQ6 9LJ"); self.assertEqual(c[0]["website"], "https://dfb.org.uk/"); self.assertIn("&", c[0]["name"])
    def test_ifan_down_fails_safe(self):
        c, st = directories.ifan(fake({})); self.assertEqual(c, []); self.assertTrue(st["status"].startswith("failed"))
    def test_ifan_schema_check(self):
        c, st = directories.ifan(fake({directories.IFAN_URL: page("<html>maintenance</html>")})); self.assertEqual(c, []); self.assertIn("schema", st["status"])
    def test_oi_skips_warm_welcome_and_parses(self):
        P = [{"_source": "warm_welcome", "title": "X", "lat": 51, "lon": 0},
             {"_source": "bham", "title": "Hall", "lat": 52.4, "lon": -1.9, "address": "1 St B18 7AF", "contact": "Website:&nbsp;https://hall.org", "hours": {"_text": "Thursday, 11:00am to 3:00pm"}}]
        c = directories.parse_oi(P, {"bham": {"title": "Birmingham", "url": "https://b.gov.uk"}})
        self.assertEqual(len(c), 1); self.assertEqual(c[0]["postcode"], "B18 7AF"); self.assertEqual(c[0]["website"], "https://hall.org")
    def test_oi_down_fails_safe(self):
        c, st = directories.open_innovations(fake({})); self.assertEqual(c, []); self.assertTrue(st["status"].startswith("failed"))
    def test_hl_down_fails_safe(self):
        c, st = directories.homeless_link(fake({})); self.assertEqual(c, []); self.assertTrue(st["status"].startswith("failed"))
    def test_hl_service_parse(self):
        h = "<p>Share Accommodation Riverside Hostel Who is the project for x Referral address 2 Road, AB1 2CD Phone 0123 Website https://rh.org Share</p>"
        c = directories.parse_hl_service("riverside-hostel", h)
        self.assertEqual((c["name"], c["postcode"], c["website"]), ("Riverside Hostel", "AB1 2CD", "https://rh.org"))

class DiscoverLayer(unittest.TestCase):
    def test_pass_becomes_tier2_fail_flagged(self):
        import tempfile, json
        h = "<p>Riverside Warm Space AB1 2CD warm space open to all, Tuesday 10am - 12pm</p>" + FILL
        cands = [{"id": "oi-1", "name": "Riverside Warm Space", "postcode": "AB1 2CD", "lat": 52, "lng": -1, "website": "https://x.org/", "directory": "OI"},
                 {"id": "oi-2", "name": "No Site Place", "postcode": "ZZ1 1ZZ", "lat": 53, "lng": -2, "website": "", "directory": "OI"}]
        unv = {}; p = tempfile.mktemp()
        add, log = discover.discover_layer(cands, [], "ws", "2026-10-21", unv, p, fake({"https://x.org/": page(h)}), geocoder=lambda pcs: {"AB1 2CD": (52, -1), "ZZ1 1ZZ": (53, -2)})
        self.assertEqual([a["id"] for a in add], ["oi-1"]); self.assertIn("oi-1", unv); self.assertEqual(unv["oi-1"]["sign_url"], "https://x.org/")
        self.assertEqual(len(log["flagged"]), 1); self.assertTrue(json.load(open(p))["flagged"])

if __name__ == "__main__": unittest.main()

class OfficeHours(unittest.TestCase):
    def test_office_hours_not_taken_as_client_times(self):
        h = "Riverside Food Bank AB1 2CD. Our office is open Monday - Friday 9am - 5pm."
        self.assertIsNone(discover.extract_times(h, "AB1 2CD"))

class OwnSiteIsMainSource(unittest.TestCase):
    OT = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}}
    def test_no_website_keeps_directory_times_unconfirmed(self):
        it = [{"id": "a", "name": "R", "postcode": "AB1 2CD", "website": "", "opening_times": dict(self.OT)}]
        discover.cross_check_times(it, "fb", "opening_times", fake({}))
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"]); self.assertEqual(it[0]["times_status"], "unconfirmed")
    def test_shelter_and_warm_space_fallback_kept_unconfirmed(self):
        for kind in ("sh", "ws"):
            it = [{"id": "s", "name": "R", "postcode": "AB1 2CD", "website": "https://x.org/", "hours": {"Tue": "10:00 - 12:00"}}]
            discover.cross_check_times(it, kind, "hours", fake({}))
            self.assertEqual(it[0]["hours"], {"Tue": "10:00 - 12:00"}); self.assertEqual(it[0]["times_status"], "unconfirmed"); self.assertNotIn("times_note", it[0])
    def test_own_site_times_override_directory(self):
        it = [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(self.OT)}]
        h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "Thursday 2pm - 4pm")
        two_runs(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))
        self.assertEqual(it[0]["opening_times"]["structured"], {"thu": [["14:00", "16:00"]]}); self.assertEqual(it[0]["times_status"], "updated")
    def test_office_like_change_reverted(self):
        it = [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(self.OT)}]
        h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "Monday - Friday 9am - 5pm")
        _, log = two_runs(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))   # held even after 2 identical runs
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertIn("office/centre hours", log["a"]["reason"])
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"]); self.assertEqual(it[0]["times_status"], "unconfirmed")
    def test_same_table_for_several_branches_reverted(self):
        it = [{"id": b, "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(self.OT)} for b in ("a", "b")]
        h = FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", "Thursday 2pm - 4pm")
        _, log = two_runs(it, "fb", "opening_times", fake({"https://x.org/": page(h)}))   # held even after 2 identical runs
        self.assertEqual({log["a"]["status"], log["b"]["status"]}, {"held_for_dean"}); self.assertIn("several branches", log["a"]["reason"])
        self.assertEqual([x["opening_times"]["structured"] for x in it], [self.OT["structured"]] * 2)
    def test_office_like_detector(self):
        self.assertTrue(discover.office_like({d: [["09:00", "17:00"]] for d in ("mon", "tue", "wed", "thu", "fri")}))
        self.assertFalse(discover.office_like({"mon": [["10:00", "12:00"]], "thu": [["13:00", "15:00"]]}))
