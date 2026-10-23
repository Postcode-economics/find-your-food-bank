"""Refresh upgrade (Dean, 23 Oct 23:36-23:42). Regression tests built from tonight's real mistakes + the new rules.
Standing rule: whenever a mistake or a missed source is found, add a test here AND fix the refresh logic in the same change."""
import json, os, sys, tempfile, unittest
from unittest import mock
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import discover as D, times_finder as TF, fill_rates as FR
from times import normalise
RYEDALE = ("Malton: Community Centre YO17 7AA Wednesday 10am - 12pm Friday 1-3pm. "
           "Pickering: Methodist Church YO18 7AA Thursday 3:30pm - 5:30pm. Kirkbymoorside: Hall YO62 6AA Thursday 9:30am - 11:30am.")
class Extract(unittest.TestCase):
    def test_ryedale_each_centre_own_times(self):   # 23 Oct: finder copied 'Friday 1-3pm' onto all three centres
        self.assertEqual(D.extract_times(RYEDALE, "YO17 7AA")["raw"], "Wednesday 10am - 12pm | Friday 1-3pm")
        self.assertEqual(D.extract_times(RYEDALE, "YO18 7AA")["raw"], "Thursday 3:30pm - 5:30pm")
        self.assertEqual(D.extract_times(RYEDALE, "YO62 6AA")["raw"], "Thursday 9:30am - 11:30am")
    def test_times_before_postcode_layout(self):
        t = "Barton Community Church Monday 12pm - 2pm OX3 9AA. The Baptist Church Thursday 10am - 11:30am OX4 1AA."
        self.assertEqual(D.extract_times(t, "OX4 1AA")["raw"], "Thursday 10am - 11:30am")
        self.assertEqual(D.extract_times(t, "OX3 9AA")["raw"], "Monday 12pm - 2pm")
    def test_unclear_layout_not_guessed(self):
        t = "Monday 12pm - 2pm Spinney Hill NN3 6BQ Tuesday 11.30am - 1.30pm Town NN1 2LZ Thursday 1pm - 2pm"
        self.assertIsNone(D.extract_times(t, "NN1 2LZ"))   # times on both sides of every postcode: could be either centre's
    def test_upper_eden_bin_hours_ignored(self):   # donation wheelie-bin times are not client hours
        t = ("You can make donations at Co-Op. There are also Wheelie Bins outside the Sands Methodist Church in Appleby on: "
             "Tuesdays 11 – 11:30am Fridays 10 – 10:30am Contact CA16 6XR")
        self.assertIsNone(D.extract_times(t, "CA16 6XR"))
    def test_donation_and_dropoff_ignored_client_kept(self):
        t = "Food parcels Wednesday 1pm - 3pm. Donation drop-off Monday 10am - 12pm. PE1 1AA"
        self.assertEqual(D.extract_times(t, "PE1 1AA")["raw"], "Wednesday 1pm - 3pm")
    def test_paddock_wood_first_saturday_kept_as_text(self):
        t = ("Normal Opening Hours - Tuesday 13:00 - 15:00 hrs, Thursday 09:30 - 11:30 hrs and the 1st Saturday of each month "
             "- 9:30 to 11:30 Paddock Wood TN12 6DS")
        ot = D.extract_times(t, "TN12 6DS")
        self.assertEqual(ot["status"], "TIMES_TEXT_ONLY")
        self.assertIn("1st Saturday of each month 9:30 to 11:30", ot["raw"]); self.assertIn("Tuesday 13:00 - 15:00", ot["raw"])
        self.assertNotIn("month 9:30", ot["raw"].replace("each month 9:30", ""))   # 'month' is not read as Monday
    def test_month_is_not_monday(self):
        self.assertIsNone(D.extract_times("Open the last week of the month 9:30 to 11:30 AB1 2CD", "AB1 2CD"))
    def test_by_appointment_kept(self):
        ot = D.extract_times("Martin Village Hall LN4 3QY Tuesday 3pm - 4pm by appointment only", "LN4 3QY")
        self.assertEqual(ot["status"], "TIMES_TEXT_ONLY"); self.assertIn("appointment", ot["raw"])
    def test_llangollen_labels_not_stripped(self):   # 'Food parcels:' / 'Community Fridge:' context must stay in the lines
        ot = normalise({"raw": "Food parcels: Wednesday 1pm - 2pm | Community Fridge: Monday and Thursday 9am - 11am", "status": "TIMES_TEXT_ONLY", "structured": None})
        self.assertEqual(ot["lines"], ["Food parcels: Wednesday 1pm - 2pm", "Community Fridge: Monday and Thursday 9am - 11am"])
        self.assertIsNone(ot["structured"])
class Decide(unittest.TestCase):
    def run_decide(self, found, items, cur=None, ks=None):
        d = tempfile.mkdtemp(); old = os.getcwd(); os.chdir(d)
        try:
            os.makedirs("overrides"); os.makedirs("logs")
            json.dump(cur or {}, open("overrides/opening_times.json", "w"))
            with mock.patch.object(TF, "known", return_value=ks or {"pages": {}, "skip": {}}):
                log = {"found": found}; TF.decide(log, items, apply=True)
            return log, json.load(open("overrides/opening_times.json")), open("reports/pending_dean.md").read()
        finally: os.chdir(old)
    def ot(self, raw="Wednesday 10am - 12pm", url="https://ex.org/where", pc="AB12CD"):
        return dict(normalise({"raw": raw, "status": "TIMES_TEXT_ONLY", "structured": None}), source_url=url, reader="times_finder", pc_seen=[pc])
    def it(self, i="ex", pc="AB1 2CD", w="https://ex.org"): return {"id": i, "name": i, "postcode": pc, "website": w}
    def test_auto_apply_off_even_for_perfect_match(self):   # Dean, 24 Oct: strict mode got 3 of 12 wrong
        log, cur, md = self.run_decide({"ex": self.ot()}, [self.it()])
        self.assertEqual(log["applied"], []); self.assertNotIn("ex", cur); self.assertIn("auto-apply is off", md)
    def test_sweep_workflow_has_no_apply(self):
        w = open(os.path.join(R, ".github", "workflows", "sweep-daily.yml")).read()
        self.assertNotIn("times_finder.py --apply", w); self.assertIn("times_finder.py --render", w)
    def test_oxford_copy_sent_to_review(self):   # same times read onto two centres with different postcodes
        f = {"a": self.ot(pc="OX39AA"), "b": self.ot(pc="OX41AA")}
        log, cur, md = self.run_decide(f, [self.it("a", "OX3 9AA"), self.it("b", "OX4 1AA")])
        self.assertEqual(log["applied"], []); self.assertNotIn("a", cur); self.assertIn("possible copy", md)
    def test_not_own_site_to_review(self):
        log, cur, _ = self.run_decide({"ex": self.ot(url="https://directory.example/x")}, [self.it()])
        self.assertFalse(log["applied"])
    def test_text_only_to_review(self):
        log, _, md = self.run_decide({"ex": self.ot(raw="first Saturday of the month 9:30am - 11:30am")}, [self.it()])
        self.assertFalse(log["applied"]); self.assertIn("first Saturday", md)
    def test_protected_never_overwritten(self):
        prot = {"ex": {"raw": "Tuesday 1pm - 3pm", "protected": True, "reader": "hand-reviewed 2026-10-23"}}
        log, cur, md = self.run_decide({"ex": self.ot()}, [self.it()], cur=prot)
        self.assertEqual(cur["ex"]["raw"], "Tuesday 1pm - 3pm"); self.assertIn("protected", md)
    def test_known_skip(self):
        ks = {"pages": {}, "skip": {"upper-eden": {"reason": "donation bin hours"}}}
        log, cur, md = self.run_decide({"upper-eden": self.ot()}, [self.it("upper-eden")], ks=ks)
        self.assertNotIn("upper-eden", cur); self.assertIn("donation bin hours", md)
class Protected(unittest.TestCase):
    def test_cross_check_flags_not_overwrites_hand_checked(self):
        ot = {"raw": "Tuesday 1pm - 3pm", "status": "TIMES_FOUND", "structured": {"tue": [["13:00", "15:00"]]}, "reader": "hand-reviewed 2026-10-23", "protected": True}
        i = {"id": "x", "website": "https://ex.org", "postcode": "AB1 2CD", "opening_times": dict(ot)}
        page = {"http": 200, "final_url": "https://ex.org/", "html": "<p>AB1 2CD Food bank open Friday 9am - 11am</p>", "sha256": "s", "etag": None, "last_modified": None}
        with mock.patch.object(D, "site_pages", return_value=(page, [("https://ex.org/", "AB1 2CD Food bank open Friday 9am - 11am")])):
            log = D.cross_check_times([i], "fb", "opening_times", fetcher=lambda u: page, threads=1)
        self.assertEqual(i["opening_times"]["raw"], "Tuesday 1pm - 3pm"); self.assertEqual(log["x"]["status"], "differs_from_hand_checked")
class Seeds(unittest.TestCase):
    def test_hand_checked_seeded_and_protected(self):
        O = json.load(open(os.path.join(R, "overrides", "opening_times.json")))
        self.assertGreaterEqual(sum(1 for v in O.values() if isinstance(v, dict) and v.get("protected")), 60)
    def test_known_sources_seeded(self):
        K = json.load(open(os.path.join(R, "overrides", "known_sources.json")))
        for k in ("upper-eden", "horsham-district/*", "readifood", "meon-valley/*", "northampton/briar-hill"): self.assertIn(k, K["skip"])
        urls = " ".join(K["pages"]); self.assertIn("swindonfoodcollective", urls); self.assertIn("ryedale", urls); self.assertIn("cefoxford", urls)
    def test_skip_wildcard(self):
        ks = {"skip": {"meon-valley/*": {"reason": "r"}}}
        self.assertEqual(TF.skipped("meon-valley/droxford", ks), "r"); self.assertIsNone(TF.skipped("meon-valleyx", ks))
class Render(unittest.TestCase):
    def test_trussell_falls_back_to_rendered_page(self):
        calls = []
        def plain(u, tries=3): return 200, u, "<html>Get emergency food</html>"
        card = ("Hucclecote Centre Part of Gloucester Foodbank 01452 Hucclecote GL3 3NR Get directions Collection only Collection times "
                "Closed today Monday-Tuesday Closed Wednesday 11:00 am to 12:45 pm Thursday-Sunday Closed See more information")
        def rend(u): calls.append(u); return 200, u, "<div>" + card + "</div>"
        with mock.patch.object(TF, "polite", side_effect=plain), mock.patch.object(TF.TT, "fetch", side_effect=plain):
            d = tempfile.mkdtemp(); old = os.getcwd(); os.chdir(d)
            try:
                os.makedirs("overrides"); json.dump({}, open("overrides/opening_times.json", "w"))
                with mock.patch.object(TF, "known", return_value={"pages": {}, "skip": {}}):
                    log = TF.run([{"id": "g/h", "name": "Hucclecote", "postcode": "GL3 3NR", "website": "https://gloucester.foodbank.org.uk/"}], render=rend, threads=1)
            finally: os.chdir(old)
        self.assertTrue(calls); self.assertEqual(log["found"]["g/h"]["structured"], {"wed": [["11:00", "12:45"]]})
class FillRates(unittest.TestCase):
    def items(self, trussell_times=True):
        it = []
        for n in range(20): it.append({"id": f"t{n}", "website": "https://x.foodbank.org.uk", "phone": "01", "opening_times": {"status": "TIMES_FOUND", "structured": {"mon": [["10:00", "12:00"]]}} if trussell_times else None})
        for n in range(10): it.append({"id": f"g{n}", "website": f"https://g{n}.org", "phone": "02", "opening_times": None})
        return it
    def test_simulated_trussell_drop_to_zero(self):
        base = FR.rates("foodbanks", self.items(True)); hist = [base] * 5
        alerts = FR.check(FR.rates("foodbanks", self.items(False)), hist)
        a = [x for x in alerts if x["source"] == "Trussell Trust pages" and x["metric"] == "times"]
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["text"], "Trussell Trust pages returned 0% opening times today, down from 100%. Possible site change.")
    def test_no_alert_when_steady_or_no_baseline(self):
        r = FR.rates("foodbanks", self.items(True))
        self.assertEqual(FR.check(r, [r] * 5), []); self.assertEqual(FR.check(FR.rates("foodbanks", self.items(False)), [r]), [])
    def test_thirty_point_rule(self):
        hist = [{"S": {"phone": [80.0, 50]}}] * 3
        self.assertTrue(FR.check({"S": {"phone": [45.0, 50]}}, hist)); self.assertFalse(FR.check({"S": {"phone": [55.0, 50]}}, hist))
        self.assertFalse(FR.check({"S": {"phone": [0.0, 50]}}, [{"S": {"phone": [15.0, 50]}}] * 3))
    def test_alert_at_top_of_daily_review_and_replaced(self):
        p = os.path.join(tempfile.mkdtemp(), "daily_review.md"); open(p, "w").write("# Daily review\nbody\n")
        a = [{"text": "Trussell Trust pages returned 0% opening times today, down from 85%. Possible site change.", "n": 1369}]
        FR.prepend_review(a, p); FR.prepend_review(a, p); s = open(p).read()
        self.assertTrue(s.startswith("<!-- fill-rate alerts -->")); self.assertEqual(s.count("down from 85%"), 1); self.assertIn("# Daily review", s)
        FR.prepend_review([], p); self.assertNotIn("fill-rate", open(p).read())
    def test_main_keeps_rolling_7(self):
        d = tempfile.mkdtemp()
        with mock.patch.object(FR, "BASE", os.path.join(d, "f.json")), mock.patch.object(FR, "REVIEW", os.path.join(d, "r.md")):
            for n in range(9): FR.main(["foodbanks"], run_id=str(n), issue=False)
            self.assertEqual(len(json.load(open(os.path.join(d, "f.json")))["runs"]), 7)
if __name__ == "__main__": unittest.main()
class FirstRunMistakes(unittest.TestCase):
    """24 Oct first strict run: 3 of 12 auto-applied were wrong. Standing rule: test + logic fix in the same change."""
    def test_giving_food_page_never_auto_applied(self):   # Hope Central Knutsford
        log, cur, md = Decide().run_decide({"k": Decide().ot(url="https://hopecentral.org.uk/get-involved/giving-food/")},
                                           [Decide().it("k", w="https://hopecentral.org.uk")])
        self.assertFalse(log["applied"]); self.assertIn("giving/donating", md)
    def test_telephone_request_kept_as_text(self):   # North Ayrshire St John's
        t = "St John's Hayocks Road Stevenston Please phone in advance to arrange a collection. Fri 12:30 - 14:00 KA20 4DE"
        ot = D.extract_times(t, "KA20 4DE")
        self.assertTrue(ot is None or ot["status"] == "TIMES_TEXT_ONLY")
    def test_seeded_skips(self):
        K = json.load(open(os.path.join(R, "overrides", "known_sources.json")))
        for k in ("sunderland/*", "north-ayrshire/st-johns-church", "hope-central/*"): self.assertIn(k, K["skip"])
    def test_guard_lets_proven_wrong_times_drop_but_keeps_place_and_phone(self):
        import refresh_guard as G
        with mock.patch.object(G, "wrong_times", return_value={"x"}):
            o = {"id": "x", "phone": "01", "opening_times": {"status": "TIMES_FOUND", "structured": {"mon": [["09:30", "11:00"]]}}}
            n = {"id": "x", "phone": "01", "opening_times": None}
            out, rep = G.guard("foodbanks", [o], [n]) if hasattr(G, "guard") else (None, None)
            if out is not None:
                self.assertIsNone([i for i in out if i["id"] == "x"][0]["opening_times"]); self.assertNotIn("x", rep["times"])
    def test_cross_check_skips_donation_pages(self):
        i = {"id": "k", "website": "https://ex.org", "postcode": "WA16 8EL", "opening_times": None}
        page = {"http": 200, "final_url": "https://ex.org/", "html": "", "sha256": "s", "etag": None, "last_modified": None}
        pages = [("https://ex.org/get-involved/giving-food/", "WA16 8EL Mondays 9.30-11am")]
        with mock.patch.object(D, "site_pages", return_value=(page, pages)):
            D.cross_check_times([i], "fb", "opening_times", fetcher=lambda u: page, threads=1)
        self.assertFalse((i.get("opening_times") or {}).get("structured"))
class FbPageKept(unittest.TestCase):
    """24 Oct: the first refresh after go-live lost 16 IFAN Facebook pages (applied before IFAN pins were added)."""
    def test_build_applies_fb_pages_after_ifan(self):
        s = open(os.path.join(R, "scripts", "build.py")).read()
        self.assertGreater(s.rindex("i['fb_page'] = fbp"), s.index("directories.ifan()"))
    def test_guard_puts_back_vanished_fb_page(self):
        import refresh_guard as G
        o = {"id": "ifan-x", "fb_page": "https://www.facebook.com/x/", "opening_times": None}
        out, rep = G.guard("foodbanks", [o], [{"id": "ifan-x", "opening_times": None}])
        self.assertEqual([i for i in out if i["id"] == "ifan-x"][0]["fb_page"], "https://www.facebook.com/x/"); self.assertIn("ifan-x", rep["fb_pages"])
class Checked9(unittest.TestCase):
    """24 Oct hand check of the 9 strict auto-applied sets: 7 correct (locked), 2 wrong (dropped, place+phone kept)."""
    def test_locked_and_dropped(self):
        O = json.load(open(os.path.join(R, "overrides", "opening_times.json")))
        for k in ("kirkcaldy/linton-lane-centre", "kirkcaldy/new-volunteer-house", "northfleet-hive-hope/disused-taxi-rank", "northfleet-hive-hope/rose-street",
                  "patch/pembroke-dock", "storehouse-influence-church/barnard-castle", "the-community-cupboard/swanley-community-cupboard"):
            self.assertTrue(O[k]["protected"]); self.assertTrue(O[k]["source_url"].startswith("https://"))
        for k in ("3food4u/budworth-hall", "dens/way-inn-christian-centre"): self.assertNotIn(k, O)
        G = json.load(open(os.path.join(R, "overrides", "guard_wrong_times.json")))["foodbanks"]
        self.assertIn("3food4u/budworth-hall", G); self.assertIn("dens/way-inn-christian-centre", G)
    def test_times_above_address_layout(self):   # 3food4u: 'Thursday 12:15pm to 1:15pm / Budworth Hall CM5 9JG / Friday 12:30pm to 2:00pm / Epping CM16 7BN'
        t = ("Wednesday 4:45pm to 6:00pm All Saints Church Hall IG7 4QD Thursday 12:15pm to 1:15pm Budworth Hall CM5 9JG "
             "Friday 12:30pm to 2:00pm Community Centre Epping CM16 7BN Waltham Abbey Baptist Church EN9 1RL")
        ot = D.extract_times(t, "CM5 9JG")
        self.assertTrue(ot is None or "Friday" not in ot["raw"])
