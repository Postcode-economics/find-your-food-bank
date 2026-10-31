"""Council ArcGIS warm-space feeds. Hermetic: the Brighton fixture never touches the network."""
import json, os, re, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import arcgis_warmspaces as A
import common
import recheck as R

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "arcgis_brighton_warm.json")
FEED_URL = "https://gis.brighton-hove.gov.uk/server/rest/services/Hosted/Warm_spaces_October_26/FeatureServer/0/query?where=1=1&outFields=*&f=json"
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d - ([01]\d|2[0-3]):[0-5]\d$")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def feed():
    return A.load_config(os.path.join(ROOT, "overrides", "arcgis_warmspaces.json"))[0]


def parsed():
    raw = json.load(open(FIXTURE, encoding="utf-8"))
    return A.parse_features(raw["features"], feed(), "2026-10-31")


class Reader(unittest.TestCase):
    def test_fixture_is_the_council_layer(self):
        raw = json.load(open(FIXTURE, encoding="utf-8"))
        self.assertEqual(len(raw["features"]), 31)
        self.assertIn("venue", {k.lower() for k in raw["features"][0]["attributes"]})

    def test_skips_no_postcode_no_times_and_term_time(self):
        records, skipped = parsed()
        why = {s["name"]: s["reason"] for s in skipped}
        self.assertEqual(why["Holy Cross Church, Woodingdean"], "no times")
        self.assertEqual(why["Holy Cross Church"], "no weekday stated")
        self.assertEqual(why["Library Community Collection (Hollingdean Community Centre)"], "no times")
        self.assertIn("term-time", why["St Leonard’s, Aldrington"])
        self.assertEqual(len(records), 27)
        self.assertTrue(all(r["postcode"] and r["hours"] for r in records))

    def test_hours_are_the_uniform_day_table(self):
        records, _ = parsed()
        by = {r["name"]: r["hours"] for r in records}
        self.assertEqual(by["Withdean Sports Complex"]["Sat"], "07:00 - 18:00")
        self.assertEqual(by["Bevendean Community Church"]["Mon"], "12:00 - 15:00")
        self.assertNotIn("Wed", by["Bevendean Community Church"])  # "Wednesday (Open house)" has no clock time
        self.assertEqual(by["Jubilee Library"]["Tue"], "10:00 - 19:00")
        self.assertEqual(by["The Hop 50+"]["Fri"], "Closed")
        self.assertEqual(by["Hove Methodist Church"], {"Fri": "10:00 - 11:30", "Sun": "10:30 - 11:30"})
        self.assertEqual(by["Woodingdean Methodist Church"], {"Thu": "10:00 - 11:30"})
        self.assertEqual(by["First Church of Christ Scientist"]["Sun"], "11:00 - 12:00")
        for rec in records:
            self.assertEqual(list(rec["hours"]), [d for d in DAYS if d in rec["hours"]], rec["name"])
            for cell in rec["hours"].values():
                if cell == "Closed":
                    continue
                for part in cell.split(" / "):
                    self.assertTrue(TIME.match(part), (rec["name"], cell))
                self.assertNotRegex(cell, r"am|pm|monday", rec["name"])

    def test_no_phone_or_council_line_is_taken_from_the_feed(self):
        records, _ = parsed()
        for rec in records:
            self.assertEqual(rec["phone"], "")
            for k in ("tel", "council_phone", "council_ooh", "council_label", "council_label_cy"):
                self.assertNotIn(k, rec)

    def test_dedupe_keeps_the_pending_id(self):
        records, _ = parsed()
        pending = [
            {"id": "ww-57952868", "name": "Jubilee Library", "postcode": "BN1 1GE"},
            {"id": "ww-55472979", "name": "Jubilee Library", "postcode": "BN1 1GE"},
            {"id": "ww-55474875", "name": "Hove Library", "postcode": "BN3 2GE"},
        ]
        kept, dupes = A.dedupe(records, pending)
        by = {r["name"]: r["id"] for r in kept}
        self.assertEqual(by["Jubilee Library"], "ww-55472979")
        self.assertEqual(by["Hove Library"], "ww-55474875")
        self.assertTrue(by["Withdean Sports Complex"].startswith("bh-"))
        self.assertEqual(dupes, [])

    def test_pagination_stops_when_the_server_says_the_page_is_complete(self):
        pages = {
            FEED_URL: {"exceededTransferLimit": True, "features": [{"attributes": {"objectid": 1}}]},
            FEED_URL + "&resultOffset=1": {"exceededTransferLimit": False, "features": [{"attributes": {"objectid": 2}}]},
        }
        got = A.fetch_features(FEED_URL, lambda url: json.dumps(pages[url]))
        self.assertEqual([f["attributes"]["objectid"] for f in got], [1, 2])

    def test_brighton_entries_pass_the_verification_gate(self):
        records, _ = parsed()
        pending = [
            {"id": "ww-55472979", "name": "Jubilee Library", "postcode": "BN1 1GE"},
            {"id": "ww-57952868", "name": "Jubilee Library", "postcode": "BN1 1GE"},
        ]
        records, _ = A.dedupe(records, pending)
        f = feed()
        verified = {r["id"]: A.evidence(r, f) for r in records}
        fresh = [{k: v for k, v in r.items() if k not in ("hours_quote", "arcgis_objectid")} for r in records]
        log = os.path.join(tempfile.mkdtemp(), "warmspaces_pending.json")
        pub, _, _ = common.verification_gate(fresh, None, verified, "2026-10-31", log, recheck=False)
        self.assertEqual({p["id"] for p in pub}, {r["id"] for r in records})
        self.assertTrue(all(p["tier"] == "verified" and p["evidence_url"] == FEED_URL for p in pub))
        self.assertTrue(all(p["hours"] for p in pub))
        # The council file has no telephone, so the publish gate still holds a brand-new row.
        import publish_gate as pg
        self.assertIn("no verified phone", pg.problems("warmspaces", pub[0]))

    def test_committed_approvals_cite_the_council_feed_and_leave_older_ones(self):
        approved = json.load(open(os.path.join(ROOT, "overrides", "approved_new_places.json"), encoding="utf-8"))
        verified = json.load(open(os.path.join(ROOT, "overrides", "warmspaces_verified.json"), encoding="utf-8"))
        self.assertIn("sheff-shipshape-community-hub", approved["warmspaces"])
        self.assertIn("bexhill/sidley", approved["foodbanks"])
        brighton = [i for i, note in approved["warmspaces"].items() if "Brighton & Hove City Council warm-space feed" in note]
        self.assertEqual(len(brighton), 27)
        held = {"bh-bn33re-the-clarendon-centre", "bh-bn12te-churchill-square"}
        for i in brighton:
            v = verified[i]
            self.assertEqual(v["evidence_url"], FEED_URL)
            self.assertTrue(v.get("day_time_quote"))
            if i in held:
                self.assertNotIn("phone", v)
            else:
                self.assertTrue(v.get("phone") and v.get("phone_source", "").startswith("https://") and v.get("phone_quote"))
        self.assertEqual(R.schema_errors({"name": "x", "lat": 50.8, "lng": -0.1, "postcode": "BN1 1GE", "address": "a",
                                           "hours": {"Sun": "Closed", "Mon": "09:00 - 17:00"}}, "ws"), [])


if __name__ == "__main__":
    unittest.main()
