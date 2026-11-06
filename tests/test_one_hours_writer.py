"""#205 is the only hours-apply path (discover.times_gate_apply / times_finder.decide, undone with times_revert.py).
own_locations used to overwrite a matched centre's times from one read of its locations page on every build, and
hours_audit --apply wrote overrides/opening_times.json directly: no 2 identical runs, no undo log. Neither writes hours now."""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import own_locations as OL
import hours_audit

URL = "https://coventry.foodbank.org.uk/locations/"
OLD = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}, "raw": "Tuesday 10am - 12pm"}
def page(days):
    rows = "".join("<p>%s</p><p>%s</p>" % (d, days.get(d, "Closed")) for d in OL.DAYS)
    return ("<h3>Riverside Hall</h3><p>Opening times</p>%s<p>Address</p><p>1 High St</p><p>CV1 2AB</p><p>Directions</p>"
            "<h3>New Hall</h3><p>Opening times</p>%s<p>Address</p><p>9 Low St</p><p>CV9 9ZZ</p><p>Directions</p>") % (rows, rows)


class OwnLocations(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "overrides"))
        json.dump({"coventry": {"url": URL}}, open(os.path.join(self.root, "overrides", "own_location_pages.json"), "w"))
    def run_(self, old, days):
        items = [{"id": "coventry/riverside", "type": "location", "name": "Riverside Hall", "postcode": "CV1 2AB", "opening_times": json.loads(json.dumps(old))}]
        log = OL.refresh(items, self.root, fetcher=lambda u: page(days), geo=lambda pcs: {p: (52.4, -1.5) for p in pcs})
        return items, log

    def test_matched_centre_keeps_its_stored_times(self):
        items, log = self.run_(OLD, {"Wed": "09:00 - 11:00"})
        ot = items[0]["opening_times"]
        self.assertEqual(ot["structured"], OLD["structured"])
        self.assertEqual(ot["raw"], OLD["raw"])
        self.assertEqual(ot["source_url"], URL)   # the gate reads exactly this page for the centre
        self.assertEqual(log["coventry"]["times_for_gate"], ["coventry/riverside"])

    def test_a_page_with_no_times_never_blanks_known_times(self):
        items, log = self.run_(OLD, {})
        self.assertEqual(items[0]["opening_times"]["structured"], OLD["structured"])
        self.assertNotIn("all_closed", items[0]["opening_times"])

    def test_an_existing_source_url_is_not_moved(self):
        items, _ = self.run_(dict(OLD, source_url="https://coventry.foodbank.org.uk/riverside/"), {"Wed": "09:00 - 11:00"})
        self.assertEqual(items[0]["opening_times"]["source_url"], "https://coventry.foodbank.org.uk/riverside/")

    def test_same_times_are_not_queued(self):
        items, log = self.run_(OLD, {"Tue": "10:00 - 12:00"})
        self.assertEqual(log["coventry"]["times_for_gate"], [])

    def test_a_centre_new_to_the_map_still_gets_the_page_record(self):
        _, log = self.run_(OLD, {"Wed": "09:00 - 11:00"})
        self.assertEqual(log["coventry"]["added"], ["coventry/new-hall"])
        snap = json.load(open(os.path.join(self.root, "overrides", "foodbank_own_pages.json")))
        self.assertEqual(snap["coventry/new-hall"]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})

    def test_matched_centre_keeps_its_address_and_pin(self):
        items = [{"id": "coventry/riverside", "type": "location", "name": "Riverside Hall", "address": "1 High St, CV1 2AB",
                  "postcode": "CV1 2AB", "lat": 52.41, "lng": -1.51, "opening_times": json.loads(json.dumps(OLD))}]
        page_moved = page({"Wed": "09:00 - 11:00"}).replace("1 High St", "99 Other Road").replace("CV1 2AB", "CV9 9ZZ")
        # page() builds both centres with the same day rows; postcode in the address line is what we compare
        log = OL.refresh(items, self.root, fetcher=lambda u: page_moved, geo=lambda pcs: {p: (52.0, -1.0) for p in pcs})
        self.assertEqual(items[0]["address"], "1 High St, CV1 2AB")
        self.assertEqual(items[0]["postcode"], "CV1 2AB")
        self.assertEqual((items[0]["lat"], items[0]["lng"]), (52.41, -1.51))
        self.assertEqual(items[0]["opening_times"]["structured"], OLD["structured"])
        text = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("address mismatch, held for Dean", text)
        self.assertIn("coventry/riverside", text)
        self.assertIn("unchanged", text)
        self.assertEqual(log["coventry"]["dropped_not_on_page"], [])

    def test_an_existing_snapshot_centre_keeps_its_place_and_times(self):
        os.makedirs(os.path.join(self.root, "overrides"), exist_ok=True)
        snap = {"coventry/new-hall": {"parent": "coventry", "name": "New Hall", "address": "9 Low St, CV9 9ZZ",
                                      "postcode": "CV9 9ZZ", "lat": 52.5, "lng": -1.4,
                                      "opening_times": {"structured": {"tue": [["10:00", "12:00"]]}, "raw": "Tue 10:00 - 12:00", "status": "TIMES_FOUND"}}}
        json.dump(snap, open(os.path.join(self.root, "overrides", "foodbank_own_pages.json"), "w"))
        items = [{"id": "coventry/riverside", "type": "location", "name": "Riverside Hall", "postcode": "CV1 2AB", "opening_times": json.loads(json.dumps(OLD))}]
        OL.refresh(items, self.root, fetcher=lambda u: page({"Wed": "09:00 - 11:00"}), geo=lambda pcs: {p: (52.4, -1.5) for p in pcs})
        got = json.load(open(os.path.join(self.root, "overrides", "foodbank_own_pages.json")))
        self.assertEqual(got["coventry/new-hall"]["address"], "9 Low St, CV9 9ZZ")
        self.assertEqual(got["coventry/new-hall"]["lat"], 52.5)
        self.assertEqual(got["coventry/new-hall"]["opening_times"]["structured"], {"tue": [["10:00", "12:00"]]})

    def test_source_has_no_times_write_on_a_matched_hit(self):
        src = open(os.path.join(ROOT, "scripts", "own_locations.py"), encoding="utf-8").read()
        self.assertNotIn("opening_times=ot", src)


class HoursAudit(unittest.TestCase):
    def test_audit_writes_no_hours(self):
        src = open(os.path.join(ROOT, "scripts", "hours_audit.py"), encoding="utf-8").read()
        self.assertFalse(hasattr(hours_audit, "apply_rows"))
        self.assertNotRegex(src, r"open\([^)]*opening_times\.json[^)]*\"w\"")
        self.assertNotIn('["opening_times"] = ', src)

    def test_apply_flag_is_refused(self):
        argv = sys.argv
        try:
            sys.argv = ["hours_audit.py", "--merge", "--apply"]
            src = open(os.path.join(ROOT, "scripts", "hours_audit.py"), encoding="utf-8").read()
            with self.assertRaises(SystemExit) as e:
                exec(compile(src, "hours_audit.py", "exec"), {"__name__": "__main__", "__file__": os.path.join(ROOT, "scripts", "hours_audit.py")})
            self.assertIn("strict gate", str(e.exception))
        finally:
            sys.argv = argv


class OneWriter(unittest.TestCase):
    """Every script that assigns opening times on an existing listing is on the #205 path or applies its output.

    publish_one.py is an overlay output-applier, like build.py: it copies already-decided
    overrides/opening_times.json with item["opening_times"] = normalise(...) and drops warehouse
    times with item["opening_times"] = None. It does not scrape sites or call times_finder.
    """
    ALLOWED = {"discover.py", "times_finder.py", "times_revert.py", "build.py", "classify.py", "publish_one.py"}
    # Subscript assignment, plus .update({...}) so a hidden write cannot skip this guard.
    PAT = re.compile(
        r"""(\[['"]opening_times['"]\]\s*=[^=]"""
        r"""|\bopening_times\s*=\s*(?!None\b)[a-z_(\[{]"""
        r"""|\.update\(\s*\{\s*['"]opening_times['"]"""
        r"""|\.update\(\s*\[\s*\(\s*['"]opening_times['"])"""
    )
    def test_no_other_script_assigns_opening_times(self):
        bad = []
        sd = os.path.join(ROOT, "scripts")
        for f in sorted(os.listdir(sd)):
            if not f.endswith(".py") or f in self.ALLOWED: continue
            for n, line in enumerate(open(os.path.join(sd, f), encoding="utf-8"), 1):
                code = line.split("#", 1)[0]
                if self.PAT.search(code) and "def " not in code: bad.append("%s:%d %s" % (f, n, line.strip()[:120]))
        self.assertEqual(bad, [])

    def test_update_cannot_hide_an_opening_times_write(self):
        self.assertIn("publish_one.py", self.ALLOWED)
        self.assertIsNotNone(self.PAT.search('item.update({"opening_times": None})'))
        self.assertIsNotNone(self.PAT.search("item.update({'opening_times': x})"))
        self.assertIsNotNone(self.PAT.search('item["opening_times"] = normalise(times[item_id])'))
        self.assertIsNotNone(self.PAT.search('item["opening_times"] = None'))
        src = open(os.path.join(ROOT, "scripts", "publish_one.py"), encoding="utf-8").read()
        hits = []
        for line in src.splitlines():
            code = line.split("#", 1)[0]
            if self.PAT.search(code) and "def " not in code:
                hits.append(code.strip())
        self.assertTrue(any('["opening_times"] = normalise(' in line for line in hits))
        self.assertTrue(any('["opening_times"] = None' in line for line in hits))
        self.assertFalse(any(".update(" in line and "opening_times" in line for line in hits))


if __name__ == "__main__":
    unittest.main()
