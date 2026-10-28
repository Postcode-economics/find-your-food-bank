"""Dean's rules (28 Oct 2026): no general council number as a venue's direct line or out-of-hours line,
and no phone change is applied without Dean's approval.

Peasholme (York) shows York's Housing Options line (01904 554500) and JNR8 Manchester shows the
council's Cost of Living line (0800 023 2692). Their own numbers are proposed in PHONES-FOR-DEAN.md
(council | current | proposed | URL | quote) and nothing changes on the map until Dean says yes.
Council-wide library lines are not changed here; they wait on Dean's review list.
"""
import json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# id -> (layer, current published number, proposed own number, page the proposed number is quoted from)
HELD = {
    "osm-node-1533578890": ("shelters", "01904 554500", "01904 551901", "https://www.york.gov.uk/homelessness/hostels-supported-housing"),
    "ww-55475981": ("warmspaces", "0800 023 2692", "0161 881 3744", "https://www.whalleyrange.org/contact-us/"),
}
def digits(s): return re.sub(r"\D", "", s or "")
def ov(name): return json.load(open(os.path.join(ROOT, "overrides", name), encoding="utf-8"))
def items(layer):
    t = open(os.path.join(ROOT, layer + ".js"), encoding="utf-8").read()
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
def dean_rows():
    t = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in t.splitlines() if l.startswith("|")]
    return rows[0], rows[2:]

class HeldForDean(unittest.TestCase):
    def test_table_columns(self):
        head, _ = dean_rows()
        self.assertEqual([h.lower() for h in head], ["council", "current", "proposed", "url", "quote"])

    def test_every_held_change_listed_with_url_and_quote(self):
        _, rows = dean_rows()
        for iid, (_, cur, new, url) in HELD.items():
            row = [r for r in rows if iid in r[0]]
            self.assertEqual(len(row), 1, iid)
            council, current, proposed, u, quote = row[0]
            self.assertIn("Council", council)
            self.assertIn(cur, current); self.assertEqual(proposed, new); self.assertEqual(u, url)
            self.assertIn(digits(new), digits(quote), iid)

    def test_current_number_still_published(self):
        for iid, (layer, cur, new, _) in HELD.items():
            x = items(layer)[iid]
            self.assertEqual(x["phone"], cur, iid); self.assertEqual(digits(x["tel"]), digits(cur), iid)
            self.assertNotEqual(digits(x["phone"]), digits(new), iid)

    def test_no_override_or_baseline_applies_the_proposed_number(self):
        b = ov("phone_baseline.json")["listings"]
        for iid, (layer, cur, new, _) in HELD.items():
            c = ov("shelters_contacts.json" if layer == "shelters" else "warmspaces_contacts.json").get(iid, {})
            self.assertNotIn(digits(new), [digits(c.get(f)) for f in ("phone", "phone_fix")], iid)
            self.assertFalse(c.get("own_page"), iid)
            self.assertEqual(b[iid]["phone"], cur, iid)
        sv = ov("shelters_verified.json")
        for iid, (layer, cur, _, _) in HELD.items():
            if layer == "shelters": self.assertEqual(sv[iid]["phone"], cur, iid)

    def test_pages_show_current_numbers(self):
        york = open(os.path.join(ROOT, "shelters", "york", "index.html"), encoding="utf-8").read()
        man = open(os.path.join(ROOT, "warm-spaces", "manchester", "index.html"), encoding="utf-8").read()
        for iid, (layer, cur, new, _) in HELD.items():
            h = york if layer == "shelters" else man
            self.assertIn("tel:" + digits(cur), h, iid); self.assertNotIn("tel:" + digits(new), h, iid)

    def test_jnr8_council_ooh_untouched(self):
        c = ov("warmspaces_contacts.json")["ww-55475981"]
        self.assertEqual(c["council_ooh"], "0161 234 5001")
        self.assertEqual(items("warmspaces")["ww-55475981"]["council_phone"], "0161 234 5001")

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
