"""Root-cause times rules (27 Oct 2026 audit). Never weaken: each case is a listing that showed wrong times."""
import json, os, sys, copy, unittest, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(R, "scripts"))
import times_guard as G, discover as D
JOINED = ("southwark norwich slough sutton peterborough nuneaton hull hackney manchester-central leeds-north-west mid-cheshire "
          "hinckley-area lowestoft-district kirkcaldy milton-keynes kingston hillingdon runcorn-district woodley wirral tameside-east "
          "stoke-on-trent southend south-east-bristol sheffield-s6 north-solihull shepway ringwood wokingham newquay anglesey "
          "thurrock salisbury").split()
def load():
    t = open(os.path.join(R, "data.full.js")).read(); return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]
class Joined(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = load(); cls.before = {i["id"]: copy.deepcopy(i) for i in cls.items}
        cls.log = G.apply(cls.items); cls.after = {i["id"]: i for i in cls.items}
    def test_listed_parents_lose_joined_centre_times(self):
        for k in JOINED:
            if k not in self.after: continue
            ot = self.after[k].get("opening_times") or {}
            if G._hand(self.before[k].get("opening_times")): continue
            with self.subTest(k):
                self.assertIn(k, self.log)
                self.assertNotIn(" | ", ot.get("raw") or "")
                self.assertNotEqual(ot.get("status"), "CLOSED")
    def test_never_closed_and_hand_reviewed_untouched(self):
        for k in self.log:
            b = self.before[k].get("opening_times")
            self.assertFalse(G._hand(b), k)
            self.assertNotIn((self.after[k]["opening_times"] or {}).get("status"), ("CLOSED", "Closed"))
    def test_cardiff_untouched(self):
        for k in self.log: self.assertFalse(k.startswith("cardiff"), k)
class Bot3Review(unittest.TestCase):
    """Bot 3 pre-check of #232 (28 Oct 00:10): 27.5% of sampled removals were wrong. Each case is a real listing."""
    @classmethod
    def setUpClass(cls):
        cls.items = load(); cls.before = {i["id"]: copy.deepcopy(i) for i in cls.items}
        cls.log = G.apply(cls.items); cls.after = {i["id"]: i for i in cls.items}
    def raw(self, k): return (self.after[k].get("opening_times") or {}).get("raw") or ""
    def test_single_own_block_kept(self):
        for k in ("dundonald", "wythenshawe", "weston-super-mare", "cheltenham", "hart", "vale", "lichfield"):
            with self.subTest(k):
                self.assertNotIn(k, self.log); self.assertEqual(self.after[k]["opening_times"], self.before[k]["opening_times"])
    def test_trim_to_own_centre(self):
        self.assertEqual(self.raw("bestwood-bulwell"), "Mon Closed Tue 13:00 - 15:00 | Wed Closed Thu 13:00 - 15:00 | Fri Closed Sat 10:00 - 12:00")
        self.assertEqual(self.raw("food-for-thought-dumbarton"), "Monday to Friday, 10am to 5pm")
    def test_watford_keeps_thursday(self):
        self.assertNotIn("watford", self.log); self.assertIn("Thu 10:00 am", self.raw("watford"))
    def test_birkenhead_operating_from(self):
        self.assertNotIn("salvation-army/birkenhead", self.log); self.assertIn("operating from 10.30am", self.raw("salvation-army/birkenhead"))
    def test_trims_drop_phone_volunteer_donation_times(self):
        self.assertEqual(self.raw("chesterfield"), ""); self.assertNotIn("9am-5pm", self.raw("chesterfield"))
        self.assertEqual(self.raw("north-lakes"), ""); self.assertEqual(self.raw("north-belfast"), "Mon 14:00 - 15:30")
        for k in ("chesterfield", "north-lakes"): self.assertNotEqual((self.after[k]["opening_times"] or {}).get("status"), "CLOSED")
    def test_rugby_middlewich_held(self):
        for k in ("rugby", "middlewich-district"):
            with self.subTest(k):
                self.assertTrue(self.log[k].startswith("held for review"))
                self.assertEqual(self.after[k]["opening_times"], self.before[k]["opening_times"])
    def test_inverness_still_dropped(self):
        self.assertEqual((self.after["salvation-army/inverness"]["opening_times"] or {}).get("status"), "NO_TIMES")
    def test_office_warehouse_postal_never_keeps_another_sites_block(self):
        # Bot 3 re-sample 2 (28 Oct): each kept another site's block, or the warehouse's own donation / office hours
        for k in ("peterborough", "arden", "chelmsford", "pbp", "doncaster", "cannock-district", "south-east-bristol"):
            with self.subTest(k):
                ot = self.after[k]["opening_times"] or {}
                self.assertEqual(ot.get("raw") or "", ""); self.assertEqual(ot.get("status"), "NO_TIMES")
                self.assertTrue(self.log[k].startswith("office/warehouse/postal"))
    def test_dartmouth_keeps_own_friday_hub(self):
        self.assertEqual(self.raw("dartmouth-district"), "Friday from 11.00 am to 12.30 pm")
    def test_weymouth_trims_to_baptist_church(self):
        self.assertEqual(self.raw("weymouth"), "Tuesday and Friday 10.30 am to 12.30pm")
    def test_rushden_keeps_own_lines(self):
        self.assertNotIn("rushden-and-higham", self.log)
        self.assertEqual(self.raw("rushden-and-higham"), "Tuesday and Thursday 9:30am – 12:30pm | Wednesday 3.30pm to 5.30pm")
    def test_burgess_hill_trims_to_church_walk(self):
        self.assertEqual(self.raw("burgess-hill"), "Tuesday and Thursday 11am - 1pm | Saturday 10am - 12pm"); self.assertNotIn("Fridays", self.raw("burgess-hill"))
    def test_split_cards_not_merged_across_week(self):
        self.assertEqual(len(G._groups(["Mon Closed Fri Closed Sat 10:00 - 12:00", "Tue Closed Sun 12:30 - 13:30"])), 2)
        self.assertEqual(len(G._groups(["Mon Closed Tue 13:00 - 15:00", "Wed Closed Thu 13:00 - 15:00"])), 1)
class Unit(unittest.TestCase):
    def test_parent_drops_centre_segment(self):
        c = {"id": "x/a", "type": "location", "opening_times": {"raw": "Mon 13:00 - 15:00", "structured": {"mon": [["13:00", "15:00"]]}}}
        p = {"id": "x", "type": "foodbank", "opening_times": {"raw": "Mon 13:00 - 15:00 | Mon Closed Tue 10:00 - 12:00 Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed", "status": "TIMES_TEXT_ONLY"}}
        log = G.apply([copy.deepcopy(p), c])
        q = copy.deepcopy(p); G.apply([q, c])  # centre's segment removed; the remaining block is the listing's own (Bot 3: trim, don't wipe)
        self.assertNotIn("Mon 13:00 - 15:00 |", q["opening_times"]["raw"]); self.assertIn("Tue 10:00 - 12:00", q["opening_times"]["raw"])
        c2 = {"id": "x/b", "type": "location", "opening_times": {"raw": "Opening times Mon Closed Tue 10:00 - 12:00 Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed", "structured": {"tue": [["10:00", "12:00"]]}}}
        log = G.apply([p, c, c2]); self.assertEqual(p["opening_times"]["status"], "NO_TIMES"); self.assertIn("x", log)
    def test_office_address_trim_gives_no_times(self):
        c = {"id": "o/a", "type": "location", "opening_times": {"raw": "Mon 13:00 - 15:00", "structured": {"mon": [["13:00", "15:00"]]}}}
        p = {"id": "o", "type": "foodbank", "address": "PO Box 1, Town", "opening_times": {"raw": "Mon 13:00 - 15:00 | Mon Closed Tue 10:00 - 12:00 Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed", "status": "TIMES_TEXT_ONLY"}}
        log = G.apply([p, c]); self.assertEqual(p["opening_times"]["status"], "NO_TIMES"); self.assertTrue(log["o"].startswith("office/warehouse/postal"))
    def test_quoted_own_line_kept_on_warehouse(self):
        G.own_lines()["zz-test"] = {"lines": ["Fri 11:00 - 12:30"]}
        try:
            p = {"id": "zz-test", "type": "foodbank", "kind": "warehouse", "opening_times": {"raw": "Fri 11:00 - 12:30 | Sun 10:00 - 12:00 | Wed 12:00 - 15:00"}}
            G.apply([p, {"id": "zz-test/a", "type": "location"}]); self.assertEqual(p["opening_times"]["raw"], "Fri 11:00 - 12:30")
        finally: G.own_lines().pop("zz-test")
    def test_warehouse_never_joined(self):
        p = {"id": "y", "type": "foodbank", "kind": "warehouse", "opening_times": {"raw": "Tue 10:00 - 12:00 | Thu 13:00 - 15:00"}}
        c = {"id": "y/a", "type": "location", "opening_times": None}
        log = G.apply([p, c])  # one run of days with its only centre: held for review, times kept (Dean 28 Oct: rugby/middlewich)
        self.assertTrue(log["y"].startswith("held")); self.assertEqual(p["opening_times"]["raw"], "Tue 10:00 - 12:00 | Thu 13:00 - 15:00")
    def test_warehouse_two_cards_wiped(self):
        p = {"id": "w", "type": "foodbank", "kind": "warehouse", "opening_times": {"raw": "Mon Closed Tue 10:00 - 12:00 | Mon Closed Tue Closed Wed Closed Thu 13:00 - 15:00"}}
        G.apply([p, {"id": "w/a", "type": "location"}, {"id": "w/b", "type": "location"}]); self.assertEqual(p["opening_times"]["status"], "NO_TIMES")
    def test_hand_reviewed_kept(self):
        ot = {"raw": "Mon 13:00 - 15:00 | Tue 10:00 - 12:00", "reader": "hand-reviewed 2026-10-27"}
        p = {"id": "z", "type": "foodbank", "kind": "warehouse", "opening_times": dict(ot)}
        G.apply([p, {"id": "z/a", "type": "location"}]); self.assertEqual(p["opening_times"], ot)
    def sa(self, raw, src="https://www.salvationarmy.org.uk/x"):
        i = {"id": "salvation-army/x", "type": "foodbank", "opening_times": {"raw": raw, "source_url": src}}
        G.apply([i]); return i["opening_times"]
    def test_sa_needs_food_wording(self):
        self.assertEqual(self.sa("Tuesday Coffee and Chat from 1pm to 2:30pm")["status"], "NO_TIMES")
        self.assertIn("Food Bank", self.sa("Food Bank Our foodbank runs from 13:00-15:00 on a Tuesday")["raw"])
    def test_sa_day_from_same_line_inverness(self):
        self.assertEqual(self.sa("Foodbank 9am - 1pm Thursday")["status"], "NO_TIMES")
    def test_sa_other_corps_page(self):
        self.assertEqual(self.sa("Food bank Friday 9.30am - 11am", "https://www.salvationarmy.org.uk/fordingbridge")["status"], "NO_TIMES")
class ProtectedReview(unittest.TestCase):
    def test_review_list_written(self):
        d = tempfile.mkdtemp()
        log = {"a": {"status": "differs_from_hand_checked", "name": "A", "site": "https://a", "kept_raw": "Tue 1-3", "new_raw": "Fri 9-11"},
               "b": {"status": "confirmed"}}
        rows = D.protected_review(log, root=d, day="2026-10-27")
        self.assertEqual([r["id"] for r in rows], ["a"])
        self.assertIn("Fri 9-11", open(os.path.join(d, "reports", "protected_times_review.md")).read())
        self.assertEqual(json.load(open(os.path.join(d, "logs", "protected_times_review.json")))["count"], 1)
    def test_flag_only_protected_true(self):
        self.assertTrue(D.is_protected({"protected": True})); self.assertFalse(D.is_protected({"reader": "times_finder"}))
if __name__ == "__main__": unittest.main()
class ProtectedAutoApply(unittest.TestCase):
    """Dean 27 Oct 23:43: protected entries update only on a proven change; everything else is held for review."""
    OT = {"raw": "Tuesday 1pm - 3pm", "status": "TIMES_FOUND", "structured": {"tue": [["13:00", "15:00"]]}, "reader": "hand-reviewed 2026-10-23", "protected": True}
    PAGE = "AB1 2CD Our food bank is open Friday 9am - 11am"
    def run1(self, pages, prev=None, day="2026-10-28", pc="AB1 2CD", kind=None, extra=None):
        from unittest import mock
        i = {"id": "x", "name": "X", "website": "https://ex.org", "postcode": pc, "opening_times": dict(self.OT)}
        if kind: i["kind"] = kind
        items = [i] + (extra or [])
        home = {"http": 200, "final_url": "https://ex.org/", "html": "<p>%s</p>" % pages[0][1], "sha256": "s", "etag": None, "last_modified": None}
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "overrides"))
        json.dump({"x": dict(self.OT)}, open(os.path.join(d, "overrides", "opening_times.json"), "w"))
        with mock.patch.object(D, "site_pages", return_value=(home, pages)):
            log = D.cross_check_times(items, "fb", "opening_times", fetcher=lambda u: home, threads=1, today=__import__("datetime").date.fromisoformat(day), pending=prev)
        D.protected_finalise(log, items, d, day)
        return i, log, d
    def prev(self, url="https://ex.org/centres/x/"):
        return {"x": {"url": url, "structured": {"fri": [["09:00", "11:00"]]}, "day": "2026-10-27"}}
    def test_proven_change_applied_with_undo(self):
        i, log, d = self.run1([("https://ex.org/centres/x/", self.PAGE)], self.prev())
        self.assertEqual(log["x"]["status"], "protected_applied", log["x"].get("proof"))
        self.assertEqual(i["opening_times"]["structured"], {"fri": [["09:00", "11:00"]]})
        self.assertTrue(i["opening_times"]["protected"]); self.assertEqual(i["opening_times"]["source_url"], "https://ex.org/centres/x/")
        O = json.load(open(os.path.join(d, "overrides", "opening_times.json")))
        self.assertEqual(O["x"]["checked_date"], "2026-10-28"); self.assertTrue(O["x"]["reader"].startswith("hand-reviewed"))
        A = json.load(open(os.path.join(d, "logs", "protected_times_applied.json")))
        self.assertEqual(A[0]["undo"]["raw"], "Tuesday 1pm - 3pm")
        md = open(os.path.join(d, "reports", "times_changes_review.md")).read()
        J = json.load(open(os.path.join(d, "logs", "times_changes_review.json")))
        self.assertEqual(J["applied"][0]["id"], "x"); self.assertEqual(J["applied"][0]["old"], "Tuesday 1pm - 3pm")
        self.assertEqual(J["applied"][0]["source_url"], "https://ex.org/centres/x/"); self.assertIn("undo", J["applied"][0])
        self.assertIn("`x`", md.split("## Held")[0]); self.assertIn("Friday 9am - 11am", md)
    def held(self, i, log, d, why):
        self.assertEqual(i["opening_times"]["raw"], "Tuesday 1pm - 3pm")
        self.assertEqual(log["x"]["status"], "differs_from_hand_checked")
        self.assertTrue(any(why in w for w in log["x"]["proof"]["why"]), log["x"]["proof"]["why"])
        self.assertIn("x", open(os.path.join(d, "reports", "protected_times_review.md")).read())
        self.assertIn("`x`", open(os.path.join(d, "reports", "times_changes_review.md")).read().split("## Held")[1])
        self.assertEqual(json.load(open(os.path.join(d, "overrides", "opening_times.json")))["x"]["raw"], "Tuesday 1pm - 3pm")
    def test_single_run_held(self):
        i, log, d = self.run1([("https://ex.org/centres/x/", self.PAGE)], None); self.held(i, log, d, "2 separate runs")
        self.assertIn("x", json.load(open(os.path.join(d, "logs", "protected_times_pending.json"))))
    def test_homepage_held(self):
        i, log, d = self.run1([("https://ex.org/", self.PAGE)], self.prev("https://ex.org/")); self.held(i, log, d, "own page")
    def test_other_location_held(self):
        page = "ZZ9 9ZZ Our food bank is open Friday 9am - 11am"
        i, log, d = self.run1([("https://ex.org/centres/y/", page)], self.prev("https://ex.org/centres/y/"))
        self.assertEqual(i["opening_times"]["raw"], "Tuesday 1pm - 3pm"); self.assertNotEqual(log["x"]["status"], "protected_applied")
        self.assertEqual(json.load(open(os.path.join(d, "overrides", "opening_times.json")))["x"]["raw"], "Tuesday 1pm - 3pm")
    def test_warehouse_held(self):
        i, log, d = self.run1([("https://ex.org/centres/x/", self.PAGE)], self.prev(), kind="warehouse"); self.held(i, log, d, "warehouse")
class NormalChangeReview(unittest.TestCase):
    def test_normal_applied_change_listed(self):
        d = tempfile.mkdtemp()
        by = {"n": {"name": "N", "opening_times": {"raw": "Wed 10am - 12pm", "source_url": "https://n.org/c/"}}}
        log = {"n": {"status": "changed", "undo": {"raw": "Mon 1pm - 3pm"}, "name": "N"}}
        a, h = D.times_changes_review(log, by, d, now="2026-10-27 23:50:00")
        self.assertEqual(a[0]["old"], "Mon 1pm - 3pm"); self.assertEqual(a[0]["new"], "Wed 10am - 12pm")
        self.assertIn("`n`", open(os.path.join(d, "reports", "times_changes_review.md")).read().split("## Held")[0])
