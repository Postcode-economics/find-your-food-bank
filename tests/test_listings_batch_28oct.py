"""Listings batch #239 (28 Oct 2026): proven own-page fixes, labels, and Dean-approved removals. Undo log: logs/listings_batch_28oct.json."""
import json, os, re, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
def J(p): return json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
def items():
    t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
REMOVED = ("salvation-army/blackburn", "salvation-army/saltcoats", "salvation-army/teignmouth", "luton/marsh-farm")
class Removals(unittest.TestCase):
    def test_removed_and_excluded_with_reason(self):
        d = items(); ex = {e["slug"]: e for e in J("overrides/foodbank_exclude.json")["foodbanks"]}
        for i in REMOVED:
            self.assertNotIn(i, d); self.assertTrue(ex[i]["exact"]); self.assertTrue(ex[i]["reason"].strip())
    def test_refresh_cannot_bring_back(self):
        src = open(os.path.join(ROOT, "scripts", "build.py"), encoding="utf-8").read()
        self.assertIn("foodbank_exclude.json", src)
        ex = J("overrides/foodbank_exclude.json")["foodbanks"]
        def excluded(i):
            return any(i == e["slug"] or (not e.get("exact") and i.startswith(e["slug"] + "/")) for e in ex)
        for i in REMOVED: self.assertTrue(excluded(i))
        self.assertFalse(excluded("salvation-army/blackburn-citadel-x"))  # exact: nothing else dropped
    def test_undo_logged(self):
        L = J("logs/listings_batch_28oct.json")["changes"]
        for i in REMOVED:
            e = [l for l in L if l["kind"] == "removed" and l["id"] == i][0]
            self.assertEqual(e["old"]["id"], i)
class Labels(unittest.TestCase):
    def test_review_section_survives_refresh(self):
        self.assertIn("'listings batch 28 oct'", open(os.path.join(ROOT, "scripts", "publish_gate.py")).read())
        pd = open(os.path.join(ROOT, "reports", "pending_dean.md")).read()
        self.assertIn("<!-- listings batch 28 oct -->", pd); self.assertIn("salvation-army/blackburn", pd)
    def test_reported_closed_kept_with_label(self):
        d = items()
        for i in ("salvation-army/southend-southchurch", "salvation-army/lochgelly", "salvation-army/thornaby",
                  "salvation-army/midsomer-norton", "salvation-army/west-cornforth", "salvation-army/wandsworth"):
            self.assertIn(i, d); self.assertTrue(d[i]["notice"].startswith("Reported closed, call before you go"), i)
            self.assertNotIn("Closed:", d[i]["notice"])
    def test_morley_and_delivery_only(self):
        d = items()
        self.assertTrue(d["salvation-army/morley"]["notice"].startswith("Leeds South & East Foodbank, voucher needed"))
        for i in ("devizes-district/pewsey", "devizes-district/marlborough"): self.assertTrue(d[i]["notice"].startswith("Delivery only"))
class Fixes(unittest.TestCase):
    def test_phones(self):
        d = items(); dg = lambda s: re.sub(r"\D", "", s or "")
        exp = {"scunthorpe/epworth-baptist-church": "03001028061", "aberdeen-south": "01224569750", "leominster": "07563000862",
               "3food4u": "07973166940", "st-monicas": "02088869568", "salvation-army/alton": "01420541778", "salvation-army/st-austell": "01726890174",
               "stroud-district/dursley": "01453367077", "rickmansworth/abbots-langley": "07716856892", "shepway/lydd": "07913573403"}
        for i, n in exp.items(): self.assertEqual(dg(d[i]["phone"]), n, i)
        self.assertEqual(d["3food4u"]["phone_label"], "WhatsApp only")
        self.assertEqual(d["stroud-district/dursley"]["phone_label"], "Food bank help line")
        self.assertFalse(d["andover/test-valley-borough-council-office"]["phone"])  # council switchboard removed, listing kept
        self.assertNotEqual(dg(d["salvation-army/andover"]["phone"]), "01264335242")  # charity shop line not applied
        B = J("overrides/phone_baseline.json")["listings"]
        for i, n in exp.items(): self.assertEqual(dg(B[i]["phone"]), n, i)
    def test_address_name_website(self):
        d = items()
        self.assertIn("RH13 9BT", d["horsham-district/hub-on-the-move-southwater"]["address"])
        self.assertIn("SP9 7EA", d["salisbury/tidworth"]["address"])
        self.assertEqual(d["south-gwynedd/penrynduedraeth"]["name"], "Penrhyndeudraeth")
        self.assertEqual(d["headley-down"]["website"], "https://www.hdcc.uk/copy-of-about-us")
        for i in ("cgcc", "crieff", "rushcliffe", "the-shack-food-project"): self.assertIn(i, d); self.assertFalse(d[i]["website"])
        W = J("overrides/foodbank_websites.json"); self.assertEqual(W["crieff"]["url"], "")
        self.assertIn("foodbank_websites.json", open(os.path.join(ROOT, "scripts", "build.py")).read())
    def test_aberdeen_north_london_corby_unchanged_address(self):
        d = items(); L = J("logs/listings_batch_28oct.json")["changes"]
        for i in ("salvation-army/aberdeen-citadel", "salvation-army/north-london", "salvation-army/corby", "salvation-army/bideford"):
            self.assertFalse([l for l in L if l["id"] == i and l["kind"] == "address"], i); self.assertTrue(d[i].get("notice"), i)
    def test_every_change_has_undo(self):
        for l in J("logs/listings_batch_28oct.json")["changes"]: self.assertIn("undo", l); self.assertIn("old", l)
if __name__ == "__main__": unittest.main()
