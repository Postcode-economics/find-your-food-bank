import sys, os, json, shutil, tempfile, unittest, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import sweep_daily as S
D = datetime.date(2026, 10, 21)
LIST = ("Warm spaces winter 2026-27. Our warm spaces this winter: "
        "Ely Community Hub – Jubilee Centre, 15a Silver Street, Ely, CB7 4JF. Opens: Thursday, 9.30am – 12pm "
        "Mepal Community Hub – Mepal Village Hall, School Lane, Mepal, Ely, CB6 2AJ. Opens: Last Thursday of every month, 10am – 12pm "
        "Contact us – Town Hall, High Street, Ely, CB7 4LQ. 01353 000000")
def page(text, http=200): return {"http": http, "text": text, "final_url": "https://example.gov.uk/warm-spaces", "last_modified": ""}
def fake_geo(pcs): return {p: {"latitude": 52.4, "longitude": 0.26} for p in pcs}
class Dates(unittest.TestCase):
    def test_season(self): self.assertTrue(S.page_dated("Open for winter 2026-27", d=D)[0])
    def test_updated(self): self.assertTrue(S.page_dated("Page last updated 2 October 2026", d=D)[0])
    def test_old_update(self): self.assertFalse(S.page_dated("Page last updated 2 October 2024", d=D)[0])
    def test_copyright_ignored(self): self.assertFalse(S.page_dated("Warm spaces list © 2026 Council", d=D)[0])
    def test_last_season(self): self.assertFalse(S.page_dated("winter 2024-25 warm spaces", d=D)[0])
class Extract(unittest.TestCase):
    def setUp(self): os.environ["SWEEP_TODAY"] = "2026-10-21"
    def test_tiers(self):
        c = {e["name"]: e for e in S.extract(LIST, "u", "src", "warmspaces", trusted=True)}
        self.assertEqual(c["Ely Community Hub"]["tier"], "verified"); self.assertEqual(c["Ely Community Hub"]["hours"], {"Thu": "09:30 - 12:00"})
        self.assertEqual(c["Mepal Community Hub"]["tier"], "unverified")   # monthly -> call before you go
        self.assertEqual(c["Contact us"]["tier"], "pending")              # not a venue name
    def test_undated_is_pending(self):
        c = S.extract(LIST.replace("winter 2026-27", ""), "u", "src", "warmspaces")
        self.assertTrue(all(e["tier"] == "pending" for e in c))
    def test_referral_flag(self):
        t = "Night shelter winter 2026-27. Hope Night Shelter – 1 Church Street, Luton, LU1 2PA. Open daily 8pm – 8am. Referral only through the council housing team."
        e = S.extract(t, "u", "src", "shelters")[0]; self.assertEqual(e["layer"], "shelters"); self.assertEqual(e["access_type"], "referral_only")
    def test_closed_skipped(self):
        t = "Warm spaces winter 2026-27. Ely Community Hub – Jubilee Centre, Ely, CB7 4JF. This hub has closed."
        self.assertEqual(S.extract(t, "u", "src", "warmspaces"), [])
NUM = ("Winter 2026-27 support. Food 1. Some Food Bank Address: 1 Road, London N7 7RY Opening times: Monday, 10am–1pm "
       "Warm Spaces 1. Andover Community Centre Address: 55–57 Corker Walk, London N7 7RY Telephone: 020 7272 3493 Opening times: Monday, 10am–1:30pm; Friday, 9:30am–5:30pm "
       "2. St Andrew’s, Thornhill Square Address: Thornhill Square, London N1 1BQ Opening times: Saturday, 11am–1pm "
       "Advice and Legal Support 1. City Advice Address: 2 Road, London N1 9PD Opening times: Tuesday, 10am–2pm")
class Parsers(unittest.TestCase):
    def setUp(self): os.environ["SWEEP_TODAY"] = "2026-10-21"
    def test_numbered_section_only(self):
        c = S.extract(NUM, "u", "src", "warmspaces", trusted=True, parser="numbered_fields", sect={"start": "Warm Spaces 1.", "end": "Advice and Legal Support 1."})
        self.assertEqual([e["name"] for e in c], ["Andover Community Centre", "St Andrew’s, Thornhill Square"])
        self.assertEqual(c[0]["hours"], {"Mon": "10:00 - 13:30", "Fri": "09:30 - 17:30"}); self.assertEqual(c[1]["tier"], "verified")
    def test_missing_section_gives_nothing(self):
        self.assertEqual(S.extract(NUM, "u", "src", "warmspaces", trusted=True, parser="numbered_fields", sect={"start": "Not on page"}), [])
    def test_label_text_rejected(self):
        t = "Winter 2026-27. Warm Spaces 1. Age UK Islington Support provided: Debt advice Address: 6 Road, London N7 6LA Opening times: Monday, 2pm–4pm"
        c = S.extract(t, "u", "src", "warmspaces", trusted=True, parser="numbered_fields")
        self.assertTrue(all(e["tier"] == "pending" for e in c))
    def test_location_fields_not_open_yet_skipped(self):
        t = ("Warm Spaces this winter, 2026 – 2027. Priors Park Community Church This space opens on 1 November 2026 – 31 March 2027 Location Priors Park Chapel, Queens Road, Tewkesbury GL20 5EY Opening hours Tuesdays 9am-4pm Activity Crafts "
             "Encounter Church This space opens on 1 October 2026 – 31 March 2027 Location Gretton Road, Cheltenham GL54 5EE Opening hours Thursdays, 12.30pm – 1.30pm Activity Lunch")
        c = S.extract(t.replace("2026 – 2027", "winter 2026-27"), "u", "src", "warmspaces", trusted=True, parser="location_fields")
        self.assertEqual([e["postcode"] for e in c], ["GL54 5EE"])
class Run(unittest.TestCase):
    def setUp(self):
        os.environ["SWEEP_TODAY"] = "2026-10-21"
        self.tmp = tempfile.mkdtemp(); ov = os.path.join(self.tmp, "overrides"); os.makedirs(ov)
        for l in ("warmspaces", "shelters"):
            json.dump([{"id": "old", "name": "Old Hall", "postcode": "CB6 2AJ"}] if l == "warmspaces" else [], open(os.path.join(ov, l + "_manual.json"), "w"))
            json.dump({}, open(os.path.join(ov, l + "_verified.json"), "w")); json.dump({}, open(os.path.join(ov, l + "_unverified.json"), "w"))
        self.saved = (S.OV, S.LOGS, S.ROOT); S.OV, S.LOGS, S.ROOT = ov, os.path.join(self.tmp, "logs"), self.tmp
    def tearDown(self): S.OV, S.LOGS, S.ROOT = self.saved; shutil.rmtree(self.tmp)
    def src(self, n=1): return {"councils": [], "lists": [{"url": f"https://example.gov.uk/warm-spaces/{i}", "name": "Test list", "layer": "warmspaces", "auto_add": True} for i in range(n)]}
    def load(self, f): return json.load(open(os.path.join(S.OV, f)))
    def test_adds_new_with_source_and_skips_dup(self):
        r = S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=fake_geo)
        man = self.load("warmspaces_manual.json"); ids = [m["id"] for m in man]
        self.assertEqual(len(r["added"]), 1)                  # Ely added; Mepal postcode already on map
        self.assertEqual(man[0]["id"], "old")                 # existing entry untouched
        new = man[-1]; self.assertTrue(new["source_url"].startswith("https://")); self.assertIn(new["id"], self.load("warmspaces_verified.json"))
        self.assertTrue(os.path.exists(os.path.join(S.LOGS, "sweep_pending.json")))
    def test_aborts_when_sources_fail(self):
        r = S.run(self.src(3), fetcher=lambda u: page("", http=503), geocoder=fake_geo)
        self.assertEqual(r["added"], []); self.assertEqual(len(self.load("warmspaces_manual.json")), 1)
    def test_holds_when_too_many(self):
        S.MAX_NEW, old = 0, S.MAX_NEW
        try: r = S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=fake_geo)
        finally: S.MAX_NEW = old
        self.assertTrue(r["status"].startswith("HELD")); self.assertEqual(len(self.load("warmspaces_manual.json")), 1)
    def test_geocoder_failure_writes_nothing(self):
        def bad(p): raise RuntimeError("down")
        r = S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=bad)
        self.assertEqual(r["added"], []); self.assertEqual(len(self.load("warmspaces_manual.json")), 1)
    def test_untrusted_source_goes_to_review(self):
        src = {"councils": [], "lists": [{"url": "https://example.gov.uk/x", "name": "Council", "layer": "warmspaces"}]}
        r = S.run(src, fetcher=lambda u: page(LIST), geocoder=fake_geo)
        self.assertEqual(r["added"], []); self.assertTrue(any(p.get("proposed_tier") == "verified" for p in r["pending"]))
    def test_past_end_date_skipped(self):
        t = "Warm spaces winter 2026-27. Ely Community Hub – Jubilee Centre, Ely, CB7 4JF. Opens: Thursday, 9.30am – 12pm until 31 March 2026"
        self.assertEqual(S.extract(t, "u", "src", "warmspaces", trusted=True), [])
    def test_exclusion_list(self):
        json.dump([{"postcode": "CB7 4JF", "name": "Ely", "reason": "rejected"}], open(os.path.join(S.OV, "sweep_exclude.json"), "w"))
        r = S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=fake_geo); self.assertEqual(r["added"], [])
    def test_idempotent(self):
        S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=fake_geo)
        r = S.run(self.src(), fetcher=lambda u: page(LIST), geocoder=fake_geo); self.assertEqual(r["added"], [])
if __name__ == "__main__": unittest.main()
