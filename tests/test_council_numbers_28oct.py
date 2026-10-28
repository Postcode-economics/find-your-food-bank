"""Dean's rules (28 Oct 2026): no general council number as a venue's direct line or out-of-hours line,
and no phone change is applied without Dean's approval.

Dean approved both at 06:55 GMT: Peasholme (York) 01904 554500 (York Housing Options) -> 01904 551901,
and JNR8 Manchester 0800 023 2692 (Cost of Living line) -> 0161 881 3744, keeping the council's
out-of-hours line 0161 234 5001. Each is applied from its own page with an undo in
logs/council_numbers_238.json, and a refresh can't put the council line back.
James House (York) is applied by listings batch #239, not here.
Council-wide library lines are not changed here; they wait on Dean's review list.
"""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts, phone_lock

# id -> (layer, old general council number, approved own number, page the number is quoted from)
APPROVED = {
    "osm-node-1533578890": ("shelters", "01904 554500", "01904 551901", "https://www.york.gov.uk/homelessness/hostels-supported-housing"),
    "ww-55475981": ("warmspaces", "0800 023 2692", "0161 881 3744", "https://www.whalleyrange.org/contact-us/"),
}
def digits(s): return re.sub(r"\D", "", s or "")
def ov(name): return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))
def items(layer):
    t = open(os.path.join(ROOT, layer + ".js"), encoding="utf-8").read()
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
def contacts(layer): return ov("shelters_contacts.json" if layer == "shelters" else "warmspaces_contacts.json")

class ApprovedNumbers(unittest.TestCase):
    def test_published(self):
        for iid, (layer, old, new, _) in APPROVED.items():
            x = items(layer)[iid]
            self.assertEqual(x["phone"], new, iid); self.assertEqual(digits(x["tel"]), digits(new), iid)

    def test_override_has_own_page_source_and_quote(self):
        for iid, (layer, old, new, src) in APPROVED.items():
            c = contacts(layer)[iid]
            self.assertEqual(c["phone_fix"], new, iid); self.assertEqual(c["phone_source"], src, iid)
            self.assertTrue(c["own_page"], iid); self.assertIn(digits(new), digits(c["phone_quote"]), iid)
        self.assertEqual(ov("shelters_verified.json")["osm-node-1533578890"]["phone"], "01904 551901")

    def test_baseline_frozen_on_new_number(self):
        b = ov("phone_baseline.json")["listings"]
        for iid, (_, _, new, _) in APPROVED.items():
            self.assertEqual(b[iid]["phone"], new, iid); self.assertEqual(b[iid]["tel"], digits(new), iid)

    def test_undo_log_entry_for_each(self):
        log = json.load(open(os.path.join(ROOT, "logs", "council_numbers_238.json"), encoding="utf-8"))["changes"]
        for iid, (layer, old, new, src) in APPROVED.items():
            e = [c for c in log if c["id"] == iid]
            self.assertEqual(len(e), 1, iid); e = e[0]
            self.assertEqual((e["layer"], e["field"], e["old"], e["new"], e["source"]), (layer, "phone", old, new, src))
            self.assertIn(digits(new), digits(e["quote"]), iid)
            self.assertEqual(e["undo"]["set"]["phone"], old); self.assertEqual(e["undo"]["set"]["tel"], digits(old))
            self.assertIn("Dean", e["note"])

    def test_refresh_cannot_restore_council_line(self):
        """A feed refresh that brings back the council line (OSM/source) ends with the venue's own number."""
        for layer in ("shelters", "warmspaces"):
            ids = {i: v for i, v in APPROVED.items() if v[0] == layer}
            tmp = tempfile.mkdtemp()
            try:
                for d in ("overrides", "reports", "logs"): os.makedirs(os.path.join(tmp, d))
                shutil.copy(os.path.join(ROOT, "overrides", "phone_baseline.json"), os.path.join(tmp, "overrides"))
                feed = [dict(id=i, name="x", phone=v[1], tel=digits(v[1])) for i, v in ids.items()]
                shelter_contacts.apply(feed, shelter_contacts.load(shelter_contacts.WS if layer == "warmspaces" else shelter_contacts.PATH))
                for x in feed: phone_lock.settle_council(x)
                phone_lock.guard(feed, tmp, via="refresh", source="test", layer=layer)
                for x in feed:
                    self.assertEqual(x["phone"], ids[x["id"]][2]); self.assertEqual(digits(x["tel"]), digits(ids[x["id"]][2]))
                raw = [dict(id=i, name="x", phone=v[1], tel=digits(v[1])) for i, v in ids.items()]
                phone_lock.guard(raw, tmp, via="refresh", source="test", layer=layer)
                for x in raw: self.assertEqual(digits(x["phone"]), digits(ids[x["id"]][2]))
            finally:
                shutil.rmtree(tmp)

    def test_pages_show_new_numbers(self):
        york = open(os.path.join(ROOT, "shelters", "york", "index.html"), encoding="utf-8").read()
        i = york.index("Peasholme")
        self.assertEqual(re.search(r'href="tel:(\d+)"', york[i:]).group(1), "01904551901")
        man = open(os.path.join(ROOT, "warm-spaces", "manchester", "index.html"), encoding="utf-8").read()
        self.assertIn("tel:01618813744", man); self.assertNotIn("tel:08000232692", man)

    def test_jnr8_council_ooh_kept(self):
        c = ov("warmspaces_contacts.json")["ww-55475981"]
        self.assertEqual(c["council_ooh"], "0161 234 5001"); self.assertEqual(c["council_phone"], "0161 234 5001")
        x = items("warmspaces")["ww-55475981"]
        self.assertEqual(x["council_phone"], "0161 234 5001")
        self.assertEqual(ov("phone_baseline.json")["listings"]["ww-55475981"]["council_ooh"], "0161 234 5001")

class LibraryLinesUnchanged(unittest.TestCase):
    """Council-wide library lines stay as they are until Dean decides; they are on his review list."""
    LIB = {"ww-68618605": "0300 123 2224", "ww-69062943": "03000 41 31 31", "ww-68737520": "0300 1234 111",
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

if __name__ == "__main__": unittest.main()
