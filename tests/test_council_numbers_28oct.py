"""Dean's rule (28 Oct 2026): no general council number as a venue's direct line or out-of-hours line.

York's Housing Options team line (01904 554500) was shown as the phone of two York shelters.
Each now shows its own number from its own page, and a refresh can't put the council line back.
Council-wide library lines are not changed here; they wait on Dean's review list.
"""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts, phone_lock

COUNCIL = "01904 554500"
OWN = {
    "osm-node-1533578890": ("01904 551901", "https://www.york.gov.uk/homelessness/hostels-supported-housing"),
    "osm-way-169564851": ("01904 553626", "https://www.york.gov.uk/homelessness/temporary-accommodation-york"),
}
def digits(s): return re.sub(r"\D", "", s or "")
def ov(name): return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))
def items(layer):
    t = open(os.path.join(ROOT, layer + ".js"), encoding="utf-8").read()
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}

class YorkShelters(unittest.TestCase):
    def test_published_own_numbers(self):
        sh = items("shelters")
        for iid, (ph, _) in OWN.items():
            self.assertEqual(sh[iid]["phone"], ph)
            self.assertNotEqual(digits(sh[iid].get("tel") or sh[iid]["phone"]), digits(COUNCIL))
        self.assertNotIn(digits(COUNCIL), json.dumps([digits(x.get("phone")) for x in sh.values()]))

    def test_override_has_own_page_source(self):
        c = ov("shelters_contacts.json")
        for iid, (ph, src) in OWN.items():
            self.assertEqual(c[iid]["phone_fix"], ph); self.assertEqual(c[iid]["phone_source"], src)
            self.assertTrue(c[iid]["own_page"]); self.assertIn(ph, c[iid]["phone_quote"])
            self.assertEqual(ov("shelters_verified.json")[iid]["phone"], ph)

    def test_baseline_frozen_on_own_number(self):
        b = ov("phone_baseline.json")["listings"]
        for iid, (ph, _) in OWN.items():
            self.assertEqual(b[iid]["phone"], ph); self.assertEqual(b[iid]["tel"], digits(ph))

    def test_refresh_cannot_restore_council_line(self):
        """A feed refresh that brings back the council line (OSM/source) ends with the venue's own number."""
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "overrides")); os.makedirs(os.path.join(tmp, "reports")); os.makedirs(os.path.join(tmp, "logs"))
            shutil.copy(os.path.join(ROOT, "overrides", "phone_baseline.json"), os.path.join(tmp, "overrides"))
            feed = [dict(id=iid, name="x", phone=COUNCIL, tel=digits(COUNCIL)) for iid in OWN]
            shelter_contacts.apply(feed)
            for x in feed: phone_lock.settle_council(x)
            phone_lock.guard(feed, tmp, via="refresh", source="test", layer="shelters")
            for x in feed:
                self.assertEqual(x["phone"], OWN[x["id"]][0]); self.assertEqual(digits(x["tel"]), digits(OWN[x["id"]][0]))
            # even without the contacts step, the frozen baseline blocks the council line
            raw = [dict(id=iid, name="x", phone=COUNCIL, tel=digits(COUNCIL)) for iid in OWN]
            phone_lock.guard(raw, tmp, via="refresh", source="test", layer="shelters")
            for x in raw: self.assertEqual(digits(x["phone"]), digits(OWN[x["id"]][0]))
        finally:
            shutil.rmtree(tmp)

    def test_york_page_shows_own_numbers(self):
        h = open(os.path.join(ROOT, "shelters", "york", "index.html"), encoding="utf-8").read()
        self.assertNotIn("tel:" + digits(COUNCIL), h)
        for ph, _ in OWN.values(): self.assertIn("tel:" + digits(ph), h)

class ManchesterJNR8(unittest.TestCase):
    def test_own_number_not_cost_of_living_line(self):
        x = items("warmspaces")["ww-55475981"]
        self.assertEqual(x["phone"], "0161 881 3744"); self.assertEqual(digits(x["tel"]), "01618813744")
        c = ov("warmspaces_contacts.json")["ww-55475981"]
        self.assertEqual(c["phone_fix"], "0161 881 3744"); self.assertTrue(c["own_page"])
        self.assertEqual(c["council_ooh"], "0161 234 5001")  # council out-of-hours line untouched
        self.assertEqual(ov("phone_baseline.json")["listings"]["ww-55475981"]["phone"], "0161 881 3744")
        h = open(os.path.join(ROOT, "warm-spaces", "manchester", "index.html"), encoding="utf-8").read()
        self.assertNotIn("tel:08000232692", h)

class LibraryLinesUnchanged(unittest.TestCase):
    """Council-wide library lines stay as they are until Dean decides; they are on his review list."""
    LIB = {"ww-69062943": "03000 41 31 31", "ww-68737520": "0300 1234 111",
           "ww-55475504": "01484 414868", "ww-69100241": "01484 414868", "ww-69100298": "01484 414868"}
    def test_unchanged_and_listed_for_dean(self):
        ws = items("warmspaces"); pd = open(os.path.join(ROOT, "reports", "pending_dean.md"), encoding="utf-8").read()
        m = re.search(r"(?s)<!-- council lines review -->.*?<!-- /council lines review -->", pd)
        self.assertTrue(m)
        for iid, ph in self.LIB.items():
            self.assertEqual(digits(ws[iid]["phone"]), digits(ph)); self.assertIn(iid, m.group(0))

    def test_publish_gate_keeps_review_section(self):
        src = open(os.path.join(ROOT, "scripts", "publish_gate.py"), encoding="utf-8").read()
        self.assertIn("'council lines review'", src)

class CouncilOohLocked(unittest.TestCase):
    def test_bruton_council_ooh_untouched(self):
        b = ov("phone_baseline.json")["listings"]["ww-68618605"]
        self.assertEqual(b["council_ooh"], "0300 123 2327")
    def test_bruton_switchboard_absent(self):
        # Dean, 28 Oct 2026 05:35 GMT: Somerset Council switchboard removed; listing kept
        ws = items("warmspaces"); self.assertIn("ww-68618605", ws)
        x = ws["ww-68618605"]; self.assertFalse(x.get("phone")); self.assertFalse(x.get("tel"))
        self.assertNotIn("03001232224", digits(str(x.get("phone", "")) + str(x.get("tel", "")) + str(x.get("council_phone", "")) + str(x.get("council_ooh", ""))))
        b = ov("phone_baseline.json")["listings"]["ww-68618605"]
        self.assertFalse(b["phone"]); self.assertFalse(b["tel"])
        h = open(os.path.join(ROOT, "warm-spaces", "somerset", "index.html"), encoding="utf-8").read() if os.path.exists(os.path.join(ROOT, "warm-spaces", "somerset", "index.html")) else ""
        self.assertNotIn("tel:03001232224", h)

if __name__ == "__main__": unittest.main()
