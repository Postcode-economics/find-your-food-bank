import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import recheck as R
PAGE = "Holy Trinity Westbury Cafe in the Church - we meet every Wednesday morning from 10.30am to 12noon. Church Road BS9 3EQ " * 3
def pg(text=PAGE, http=200, final="https://www.example.org/p", etag="a"):
    import hashlib
    return {"http": http, "text": text, "final_url": final, "etag": etag, "last_modified": "", "sha256": hashlib.sha256(text.encode()).hexdigest()}
E = {"id": "x1", "name": "Cafe in the Church", "postcode": "BS9 3EQ", "address": "Church Road", "lat": 51.49, "lng": -2.62, "hours": {"Wed": "10:30 - 12:00"}}
OV = {"name": "Cafe in the Church", "evidence_url": "https://example.org/p", "day_time_quote": "every Wednesday morning from 10.30am to 12noon"}
class T(unittest.TestCase):
    def test_confirmed(self): self.assertTrue(R.check(E, OV, pg(), "https://example.org/p")["ok"])
    def test_unreachable(self): self.assertFalse(R.check(E, OV, pg(text="", http=404), OV["evidence_url"])["ok"])
    def test_redirect_other_site(self):
        r = R.check(E, OV, pg(final="https://parked-domain.com/"), OV["evidence_url"]); self.assertFalse(r["ok"]); self.assertIn("different site", r["reason"])
    def test_times_gone(self):
        r = R.check(E, OV, pg(text=PAGE.replace("10.30am to 12noon", "TBC")), OV["evidence_url"]); self.assertFalse(r["ok"]); self.assertIn("times", r["reason"])
    def test_day_gone(self):
        r = R.check(E, OV, pg(text=PAGE.replace("Wednesday", "")), OV["evidence_url"]); self.assertFalse(r["ok"])
    def test_closed(self):
        r = R.check(E, OV, pg(text=PAGE + " This cafe has closed."), OV["evidence_url"]); self.assertFalse(r["ok"])
    def test_name_gone(self):
        r = R.check(E, OV, pg(text="Some other page entirely about gardening clubs " * 10), OV["evidence_url"]); self.assertFalse(r["ok"])
    def test_change_detection(self):
        r = R.check(E, OV, pg(text=PAGE + " new"), OV["evidence_url"], prev={"sha256": "old", "etag": "a", "last_modified": ""})
        self.assertTrue(r["changed_since_last_run"]); self.assertTrue(r["ok"])
    def test_schema(self):
        self.assertEqual(R.schema_errors(E, "ws"), [])
        self.assertTrue(R.schema_errors(dict(E, hours={"Wed": "1030-12"}), "ws"))
        self.assertTrue(R.schema_errors(dict(E, lat=10), "ws"))
        self.assertTrue(R.schema_errors(dict(E, postcode="NOTAPC"), "ws"))
        self.assertTrue(R.schema_errors(dict(E, access_type="referral_only", referral=""), "sh"))
        self.assertTrue(R.schema_errors(dict(E, flag_closed=True), "sh"))
    def test_recheck_all_omits_failures(self):
        d = tempfile.mkdtemp(); log = os.path.join(d, "warmspaces_recheck.json")
        pages = {"https://example.org/p": pg(), "https://example.org/gone": pg(text="", http=500)}
        out = R.recheck_all([E, dict(E, id="x2")], {"x1": OV, "x2": dict(OV, evidence_url="https://example.org/gone")}, {}, log, "ws", fetcher=lambda u: pages[u])
        self.assertTrue(out["x1"]["ok"]); self.assertFalse(out["x2"]["ok"]); self.assertTrue(json.load(open(log))["_run"]["fetched_at"])
    def test_norm_times(self): self.assertEqual(R.norm_times("10.30am to 12pm, 5pm-10am"), {"10:30", "12:00", "17:00", "10:00"})
    def test_blank_hours_skips_time_match(self):
        e = dict(E, hours="")
        ov = dict(OV, day_time_quote="Call Mon-Fri 9am to 5pm")
        t = PAGE.replace("10.30am to 12noon", "nothing matching office hours")
        self.assertTrue(R.check(e, ov, pg(text=t), OV["evidence_url"])["ok"])
if __name__ == "__main__": unittest.main()

class OsmOnly(unittest.TestCase):
    """'100% categorically': OSM-sourced entries need their own-site page to show this place's postcode/address."""
    OE = dict(E, id="osm-way-1", source="OpenStreetMap")
    def test_osm_with_postcode_ok(self): self.assertTrue(R.check(self.OE, OV, pg(), OV["evidence_url"])["ok"])
    def test_osm_without_address_fails(self):
        t = PAGE.replace("BS9 3EQ", "").replace("Church Road", "")
        r = R.check(self.OE, OV, pg(text=t), OV["evidence_url"]); self.assertFalse(r["ok"]); self.assertIn("OpenStreetMap-only", r["reason"])
        self.assertTrue(R.check(E, OV, pg(text=t), OV["evidence_url"])["ok"])  # non-OSM entries keep the existing rule
    def test_osm_page_rejected(self):
        u = "https://www.openstreetmap.org/way/1"
        r = R.check(self.OE, OV, pg(final=u), u); self.assertFalse(r["ok"])
class Http200Reason(unittest.TestCase):
    def test_short_200_not_called_unreachable(self):
        r = R.check(E, OV, pg(text="One moment, please"), OV["evidence_url"]); self.assertFalse(r["ok"])
        self.assertNotIn("unreachable", r["reason"]); self.assertIn("no readable text", r["reason"])
    def test_real_unreachable(self):
        self.assertIn("unreachable this run (HTTP 403)", R.check(E, OV, pg(text="", http=403), OV["evidence_url"])["reason"])
    def test_24_hours_schema(self):
        self.assertEqual(R.schema_errors(dict(E, hours={"Mon": "24 hours"}), "sh"), [])
class Http2xx(unittest.TestCase):
    def test_202_not_unreachable(self):
        r = R.check(E, OV, pg(http=202), OV["evidence_url"]); self.assertFalse(r["ok"]); self.assertIn("did not return the page", r["reason"])
