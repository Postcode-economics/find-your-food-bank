import sys, os, json, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fb_recheck as F
GF = "https://www.givefood.org.uk/needs/at/%s/"
def item(**k):
    x = dict(id="acme", type="foodbank", name="Acme Foodbank", foodbank="Acme Foodbank", network="", address="1 High St", postcode="AB1 2CD",
             lat=52.0, lng=-1.0, phone="01234 567890", website="https://acme.org.uk/", givefood=GF % "acme", opening_times=None)
    x.update(k); return x
META = {"foodbanks": {"http": 200, "final_url": "https://www.givefood.org.uk/api/2/foodbanks/", "etag": "e1", "last_modified": "", "sha256": "s1", "fetched_at": "t"}}
def page(text="Acme Foodbank needs", http=200, final="https://www.givefood.org.uk/needs/at/acme/"): return {"http": http, "final_url": final, "text": text, "sha256": "x"}
class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.log = os.path.join(self.d, "r.json"); self.pend = os.path.join(self.d, "p.json")
    def run_gate(self, items, records=None, meta=None, fetcher=None, per_run=0):
        records = records if records is not None else {i["id"]: {"slug": i["id"]} for i in items}
        return F.gate(items, records, json.loads(json.dumps(meta or META)), self.log, self.pend, fetcher=fetcher or (lambda u: page()), per_run=per_run, run_key="k")
    def test_clean_passes_and_stamps(self):
        pub, om = self.run_gate([item()]); self.assertEqual(len(pub), 1); self.assertFalse(om)
        log = json.load(open(self.log)); self.assertTrue(log["acme"]["ok"]); self.assertEqual(pub[0]["fetched_at"], log["_run"]["fetched_at"])
        self.assertTrue(log["acme"]["record_sha256"])
    def test_api_not_200_stops_run(self):
        m = json.loads(json.dumps(META)); m["foodbanks"]["http"] = 503
        with self.assertRaises(RuntimeError): self.run_gate([item()], meta=m)
    def test_api_redirect_elsewhere_stops_run(self):
        m = json.loads(json.dumps(META)); m["foodbanks"]["final_url"] = "https://parked.example/"
        with self.assertRaises(RuntimeError): self.run_gate([item()], meta=m)
    def test_change_detection(self):
        self.run_gate([item()], records={"acme": {"v": 1}})
        m = json.loads(json.dumps(META)); m["foodbanks"]["sha256"] = "s2"; m["foodbanks"]["etag"] = "e2"
        self.run_gate([item()], records={"acme": {"v": 2}}, meta=m)
        log = json.load(open(self.log)); self.assertTrue(log["acme"]["changed_since_last_run"])
        self.assertTrue(log["_run"]["api"]["foodbanks"]["changed_since_last_run"]); self.assertTrue(log["_run"]["api"]["foodbanks"]["headers_changed"])
    def test_schema_failures_left_off(self):
        for bad in (dict(lat=10.0), dict(postcode="NOTAPC"), dict(name=""), dict(type="x"), dict(website="javascript:x"),
                    dict(givefood="https://evil.example/needs/at/acme/"),
                    dict(opening_times={"status": "TIMES_FOUND", "structured": {"wed": [["09:00", "10:00"]], "mon": [["09:00", "10:00"]]}}),
                    dict(opening_times={"status": "TIMES_FOUND", "structured": {"mon": [["9am", "10:00"]]}}),
                    dict(label_en="Distribution centre – drop off food only")):
            pub, om = self.run_gate([item(**bad)]); self.assertFalse(pub, bad); self.assertIn("schema", om[0]["reason"])
    def test_no_source_record_left_off(self):
        pub, om = self.run_gate([item()], records={}); self.assertFalse(pub); self.assertIn("no source record", om[0]["reason"])
    def test_source_url_must_be_this_record(self):
        pub, om = self.run_gate([item(givefood=GF % "other")]); self.assertFalse(pub); self.assertIn("source URL", om[0]["reason"])
        pub, _ = self.run_gate([item(id="acme/hall", type="location", givefood="https://www.givefood.org.uk/needs/at/acme/hall/")]); self.assertEqual(len(pub), 1)
    def test_live_page_must_name_it(self):
        pub, om = self.run_gate([item()], fetcher=lambda u: page(text="Some other charity"), per_run=5); self.assertFalse(pub)
        pub, om = self.run_gate([item()], fetcher=lambda u: page(http=429), per_run=5); self.assertEqual(len(pub), 1)
        self.assertTrue(json.load(open(self.log))["acme"]["flags"])
    def test_ifan_needs_own_site_200(self):
        i = item(id="ifan-x", givefood="", directory="IFAN", own_site_check={"http": 403, "final_url": "https://x.org"})
        pub, om = self.run_gate([i]); self.assertFalse(pub)
        i["own_site_check"]["http"] = 200; pub, _ = self.run_gate([i]); self.assertEqual(len(pub), 1)
    def test_labels(self):
        self.assertFalse(F.schema_errors(item(label_en="Donations only", label_cy="Rhoddion yn unig")))
        self.assertFalse(F.schema_errors(item(label_en="Warehouse – donations only. Clients cannot visit here.", label_cy="Warws", locked=True)))
    def test_no_address_flagged_not_dropped(self):
        pub, _ = self.run_gate([item(address="", postcode="")]); self.assertEqual(len(pub), 1)
        self.assertTrue(json.load(open(self.log))["acme"]["flags"])
    def test_channel_islands_ok(self):
        self.assertFalse(F.schema_errors(item(lat=49.186, lng=-2.10, postcode="JE2 4WH")))
if __name__ == "__main__": unittest.main()
class Manual(unittest.TestCase):
    def test_extra_location_uses_evidence_url(self):
        import tempfile; d = tempfile.mkdtemp()
        i = item(id="rugby/lawn", type="location", manual=True, evidence_url="https://rugby.foodbank.org.uk/locations/", givefood=GF % "rugby")
        pub, _ = F.gate([i], {"rugby/lawn": {"name": "x"}}, json.loads(json.dumps(META)), d + "/r", d + "/p", fetcher=lambda u: page(), per_run=0, run_key="k")
        self.assertEqual(len(pub), 1); self.assertEqual(json.load(open(d + "/r"))["rugby/lawn"]["source_url"], "https://rugby.foodbank.org.uk/locations/")
        pub, om = F.gate([dict(i)], {}, json.loads(json.dumps(META)), d + "/r", d + "/p", fetcher=lambda u: page(), per_run=0, run_key="k")
        self.assertFalse(pub)
