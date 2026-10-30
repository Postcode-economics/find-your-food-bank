"""Approved listing fixes, kept by the 3x-daily refresh (overrides, not a one-off edit of data.js).

Checked on each organisation's own site on 26 Oct 2026. Where the site disagreed with the
requested wording, the site wins and the test records that.
"""
import csv, json, os, sys, unittest
from unittest import mock
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import classify, shelter_contacts as sc
from times import normalise

def J(name):
    return json.load(open(os.path.join(ROOT, "overrides", name)))

def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]

def excluded(i, excl):
    host = (i.get("website") or "").split("//")[-1].split("/")[0].lower().removeprefix("www.")
    return any(i["id"] == e["slug"] or (not e.get("exact") and (i["id"].startswith(e["slug"] + "/") or (e.get("host") and host == e["host"]))) for e in excl)

def after_refresh(rows=None):
    """The parts of scripts/build.py that re-apply these overrides on every run."""
    rows = items() if rows is None else rows
    times = J("opening_times.json")
    for i in rows:
        if i["id"] in times:
            i["opening_times"] = normalise(times[i["id"]])
    classify.classify(rows, ROOT)
    notices = J("foodbank_notices.json")
    for i in rows:
        n = notices.get(i["id"])
        if isinstance(n, dict) and n.get("notice"):
            i["notice"] = n["notice"]
    excl = J("foodbank_exclude.json").get("foodbanks", [])
    return [i for i in rows if not excluded(i, excl)]

def by_id(rows):
    return {i["id"]: i for i in rows}

class Kirkcaldy(unittest.TestCase):
    def test_viewforth_pin_replaced_by_three_centres(self):
        d = by_id(after_refresh())
        self.assertNotIn("kirkcaldy", d)  # Viewforth KY1 3BW is not on the contact page
        park = d["kirkcaldy/park-road-centre"]
        self.assertEqual(park["postcode"], "KY1 3EL")
        self.assertIn("2 Park Road", park["address"])
        self.assertEqual(park["opening_times"]["structured"], {
            "mon": [["10:00", "15:00"]], "tue": [["10:00", "13:00"]],
            "wed": [["10:00", "13:00"]], "thu": [["10:00", "15:00"]]})
        self.assertEqual(d["kirkcaldy/linton-lane-centre"]["postcode"], "KY2 6LF")
        self.assertIn("Portacabin", d["kirkcaldy/linton-lane-centre"]["address"])
        self.assertEqual(d["kirkcaldy/new-volunteer-house"]["postcode"], "KY1 1XT")
        self.assertIn("16 East Fergus Place", d["kirkcaldy/new-volunteer-house"]["address"])
        # Link Living is still on the contact page, marked agency referrals only, so the pin stays.
        self.assertIn("kirkcaldy/link-living", d)
        rule = next(e for e in J("foodbank_exclude.json")["foodbanks"] if e["slug"] == "kirkcaldy")
        self.assertTrue(rule.get("exact"))  # drops only the Viewforth pin; the centre pins stay

    def test_existing_centre_hours_not_weakened(self):
        ot = J("opening_times.json")
        self.assertTrue(ot["kirkcaldy/linton-lane-centre"]["protected"])
        self.assertTrue(ot["kirkcaldy/new-volunteer-house"]["protected"])
        self.assertEqual(ot["kirkcaldy/new-volunteer-house"]["raw"],
                         "Monday 10am - 12:30pm | Wednesday 10am - 12:30pm | Friday 10am - 12:30pm")
        self.assertEqual(ot["kirkcaldy/linton-lane-centre"]["raw"],
                         "Monday 10am - 12:30pm | Tuesday 10am - 12:30pm | Thursday 10am - 12:30pm | Friday 10am - 12:30pm")
        self.assertTrue(ot["kirkcaldy/linton-lane-centre"]["source_url"].startswith("https://www.kirkcaldyfoodbankcharity.org.uk/"))

    def test_new_volunteer_house_and_park_road_are_walk_in(self):
        import build_access as ba
        found = {}
        for f in ("voucher_split_ifan_final.csv", "voucher_split_indep.csv"):
            for r in csv.DictReader(open(os.path.join(ROOT, "overrides", "access", f), encoding="utf-8")):
                if r["id"] in ("kirkcaldy/new-volunteer-house", "kirkcaldy/park-road-centre", "kirkcaldy/link-living", "kirkcaldy/linton-lane-centre"):
                    found[r["id"]] = ba.classify(r)
        self.assertEqual(found["kirkcaldy/new-volunteer-house"], "walkin")
        self.assertEqual(found["kirkcaldy/park-road-centre"], "walkin")
        self.assertEqual(found["kirkcaldy/linton-lane-centre"], "walkin")
        self.assertEqual(found["kirkcaldy/link-living"], "voucher")

class Southend(unittest.TestCase):
    def test_friendship_house_is_donations_only_and_points_at_the_four_verified_centres(self):
        """The food bank's own page lists 4 distribution centres, not 8. The other Give Food pins are excluded."""
        d = by_id(after_refresh())
        s = d["southend"]
        self.assertEqual(s["kind"], "warehouse")
        self.assertEqual(s["label_en"], "Donations only")
        self.assertEqual(s["postcode"], "SS1 2QA")
        self.assertEqual({c["id"] for c in s["centres"]}, {
            "southend/hawkwell-hockley", "southend/belle-vue-baptist-church",
            "southend/westcliff", "southend/shoeburyness"})
        for gone in ("southend/leigh", "southend/leigh-road-baptist-church", "southend/earls-hall", "southend/eastwood"):
            self.assertNotIn(gone, d)
        self.assertEqual(d["southend/hawkwell-hockley"]["opening_times"]["structured"], {"mon": [["17:00", "18:30"]]})
        self.assertEqual(d["southend/belle-vue-baptist-church"]["opening_times"]["structured"], {"tue": [["13:00", "15:00"]]})
        self.assertEqual(d["southend/westcliff"]["opening_times"]["structured"], {"wed": [["13:00", "15:00"]]})
        self.assertEqual(d["southend/shoeburyness"]["opening_times"]["structured"], {"thu": [["12:30", "14:30"]]})
        self.assertIn("Donations only", d["southend"]["opening_times"]["raw"])

class KingsLangley(unittest.TestCase):
    def test_all_saints_stays_a_tuesday_session(self):
        """Own community page: Tuesday 10am-11.30am, anyone in need can take food. Not donations only."""
        d = by_id(after_refresh())
        k = d["kings-langley"]
        self.assertNotEqual(k.get("kind"), "warehouse")
        self.assertIsNone(k.get("label_en"))
        self.assertEqual(k["opening_times"]["structured"], {"tue": [["10:00", "11:30"]]})
        self.assertEqual(k["opening_times"]["source_url"], "https://beneficeoflangelei.org.uk/allsaints/community/")
        a = d["kings-langley/apsley"]
        self.assertEqual(a["postcode"], "HP3 9SB")
        self.assertIn("Apsley Community Centre", a["address"])
        self.assertEqual(a["opening_times"]["structured"], {"mon": [["15:30", "17:30"]], "thu": [["10:00", "12:00"]]})
        self.assertIn("kings-langley/bennetts-end", d)  # still the Bennetts End pin; 2026 hours were not on a current page

class GalashielsHelensburgh(unittest.TestCase):
    def test_emergency_walk_in_and_hub_hours(self):
        d = by_id(after_refresh())
        g = d["galashiels-and-area"]
        self.assertNotEqual(g.get("kind"), "warehouse")
        self.assertEqual(g["opening_times"]["structured"]["wed"], [["13:00", "14:45"]])
        self.assertEqual(g["opening_times"]["structured"]["thu"], [["17:00", "18:00"]])
        self.assertIn("Emergency walk-in", g["notice"])
        self.assertIn("1.00", g["notice"])
        h = d["helensburgh-lomond"]
        self.assertNotEqual(h.get("kind"), "warehouse")
        self.assertEqual(h["opening_times"]["structured"], {"mon": [["10:00", "12:00"]], "thu": [["15:00", "19:00"]]})
        self.assertEqual(d["helensburgh-lomond/st-modans-church-community-centre"]["opening_times"]["structured"], {"wed": [["13:00", "15:00"]]})
        import build_access as ba
        tags = {}
        for r in csv.DictReader(open(os.path.join(ROOT, "overrides", "access", "voucher_split_indep.csv"), encoding="utf-8")):
            if r["id"] in ("galashiels-and-area", "helensburgh-lomond", "kings-langley"):
                tags[r["id"]] = ba.classify(r)
        self.assertEqual(tags, {"galashiels-and-area": "walkin", "helensburgh-lomond": "walkin", "kings-langley": "walkin"})

    def test_hand_reviewed_hours_are_not_overwritten(self):
        import discover as D
        ot = J("opening_times.json")["galashiels-and-area"]
        i = {"id": "galashiels-and-area", "website": "https://galashielsfoodbank.wordpress.com/", "postcode": "TD1 3HS",
             "opening_times": dict(ot)}
        page = {"http": 200, "final_url": "https://galashielsfoodbank.wordpress.com/", "html": "", "sha256": "s", "etag": None, "last_modified": None}
        text = "TD1 3HS Food bank open Friday 9am - 11am"
        with mock.patch.object(D, "site_pages", return_value=(page, [("https://galashielsfoodbank.wordpress.com/", text)])):
            log = D.cross_check_times([i], "fb", "opening_times", fetcher=lambda u: page, threads=1)
        self.assertEqual(i["opening_times"]["structured"]["wed"], [["13:00", "14:45"]])
        self.assertEqual(log["galashiels-and-area"]["status"], "differs_from_hand_checked")

class StMonicas(unittest.TestCase):
    def test_phone_labelled_as_portsmouth_churches_housing_association(self):
        data = sc.load()
        o = data["sa-st-monica-s-house-lifehouse"]
        self.assertEqual(o["phone_fix"], "023 9282 5673")
        self.assertEqual(o["phone_label"], "Portsmouth Churches Housing Association number")
        it = [{"id": "sa-st-monica-s-house-lifehouse", "phone": "023 9282 5673 or 023 9229 7877", "tel": "02392825673"}]
        sc.apply(it, data)
        self.assertEqual(it[0]["phone"], "023 9282 5673")
        self.assertEqual(it[0]["tel"], "02392825673")
        self.assertEqual(it[0]["phone_label"], "Portsmouth Churches Housing Association number")
        self.assertIn("i.phone_label?", open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read())
        import build_seo as B
        card = B.card_sh({"name": "St Monica's House Lifehouse", "address": "Lucknow Street", "postcode": "PO1 1PT",
                           "phone": "023 9282 5673", "tel": "02392825673", "phone_label": o["phone_label"], "hours": "By referral, call to arrange"})
        self.assertIn("023 9282 5673", card)
        self.assertIn("Portsmouth Churches Housing Association number", card)

class LambethLarder(unittest.TestCase):
    LID = "ifan-a2fb0701e0208ee9e642a3-0"

    def test_not_on_published_map(self):
        self.assertNotIn(self.LID, by_id(items()))

    def test_stays_off_after_refresh_exclusion_filter(self):
        self.assertNotIn(self.LID, by_id(after_refresh()))

    def test_exclude_rule(self):
        rule = next(e for e in J("foodbank_exclude.json")["foodbanks"] if e["slug"] == self.LID)
        self.assertTrue(rule.get("exact"))
        self.assertEqual(rule["reason"], "not a food bank (directory), Dean 29 Oct")
        self.assertEqual(rule.get("host"), "lambethlarder.org")

    def test_refresh_guard_does_not_restore(self):
        import refresh_guard as g
        old = {"id": self.LID, "name": "Lambeth Larder", "lat": 51.463981, "lng": -0.113021,
               "website": "https://www.lambethlarder.org", "postcode": "SW9 7QD"}
        new = [i for i in items() if i["id"] != self.LID]
        out, rep = g.guard("foodbanks", [old], new)
        self.assertNotIn(self.LID, {i["id"] for i in out})
        self.assertEqual(rep.get("places"), [])

if __name__ == "__main__":
    unittest.main()
