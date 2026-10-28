"""Salvation Army phones (28 Oct 2026, listings batch #239): all 32 'page number correct' rows in
reports/salvation-army-phones.csv are applied from the corps' own 'Where we are' block (same number on both reads),
including the 14 named officers' numbers (Dean 28 Oct: a named person's number is OK if the organisation's own page
publishes it). The 3 'unclear' rows (Hartlepool, Blackpool South, Barnstaple) are not touched."""
import csv, json, os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import phone_rule
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
dg = lambda s: re.sub(r"\D", "", s or "")
def layer(f):
    t = open(os.path.join(ROOT, f), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
ROWS = list(csv.DictReader(open(os.path.join(ROOT, "reports", "salvation-army-phones.csv"), encoding="utf-8")))
NEW = {
    "salvation-army/aberystwyth": "07774625842", "salvation-army/alton": "01420541778", "salvation-army/ballymena": "07918402788",
    "salvation-army/barton-upon-humber": "01652637312", "salvation-army/belfast-north": "02890744043", "salvation-army/bicester": "01869221924",
    "salvation-army/buckingham": "07786998586", "salvation-army/bury-st-edmunds": "01284768031", "salvation-army/chester": "01244316791",
    "salvation-army/colchester-mount-zion": "07443193101", "salvation-army/connahs-quay": "01244823984", "salvation-army/consett": "01207501712",
    "salvation-army/cwm": "07833017366", "salvation-army/deal": "07469659218", "salvation-army/east-kilbride": "01355234366",
    "salvation-army/eaton-bray": "01525222087", "salvation-army/exeter-temple": "01392346817", "salvation-army/fort-william": "07501936833",
    "salvation-army/ilfracombe": "07918564835", "salvation-army/leadgate": "01207508805", "salvation-army/leek": "01538387245",
    "salvation-army/loughborough": "01509262768", "salvation-army/maldon": "07831129749", "salvation-army/north-walsham": "07587410690",
    "salvation-army/nottingham-aspley": "07831142652", "salvation-army/nottingham-meadows": "07831148316",
    "salvation-army/nottingham-william-booth-memorial-complex": "07587348459", "salvation-army/parkhead": "07810059682",
    "salvation-army/potton": "01767261138", "salvation-army/shildon": "01388777358", "salvation-army/sittingbourne": "07775906098",
    "salvation-army/south-shields": "01914553710",
}
REMOVED_DUPLICATES = {"salvation-army/connahs-quay", "salvation-army/ilfracombe", "salvation-army/shildon"}
UNCLEAR = {"salvation-army/hartlepool": "01429272462", "salvation-army/blackpool-south": "01253348347", "salvation-army/barnstaple": "01271321972"}

class SalvationArmyPhones(unittest.TestCase):
    def test_report_rows_match(self):
        correct = {r["listing id"]: r for r in ROWS if r["classification"] == "page number correct"}
        self.assertEqual(len(correct), 32); self.assertEqual(set(correct), set(NEW))
        self.assertEqual(sum(r["number_type"] == "named person's mobile" for r in correct.values()), 14)
        self.assertEqual({r["listing id"] for r in ROWS if r["classification"] == "unclear"}, set(UNCLEAR))
        for i, r in correct.items():
            self.assertEqual(dg(r["page phone (read 1)"]), NEW[i]); self.assertEqual(dg(r["page phone (read 2)"]), NEW[i])
            self.assertEqual(r["reads agree"], "yes")
            self.assertEqual(r["corps page URL"], "https://www.salvationarmy.org.uk/" + i.split("/", 1)[1])

    def test_applied_on_the_map(self):
        d = layer("data.full.js")
        for i, n in NEW.items():
            if i in REMOVED_DUPLICATES:
                self.assertNotIn(i, d); continue
            self.assertEqual((dg(d[i]["phone"]), dg(d[i]["tel"])), (n, n), i)
        self.assertEqual(dg(d["salvation-army/east-kilbride"]["phone"]), "01355234366")
        self.assertNotIn("01335234366", json.dumps(d["salvation-army/east-kilbride"]))

    def test_compact_data_and_exports(self):
        s = open(os.path.join(ROOT, "data.js"), encoding="utf-8").read()
        ex = {r["id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "export", "foodbanks.csv"), encoding="utf-8", newline=""))}
        exj = {r["id"]: r for r in J("export/foodbanks.json")["items"]}
        for i, n in NEW.items():
            if i in REMOVED_DUPLICATES: continue
            self.assertIn(n, s, i); self.assertEqual(dg(ex[i]["phone"]), n, i); self.assertEqual(dg(exj[i]["phone"]), n, i)

    def test_overrides_baseline_and_source(self):
        ph, src, base = J("overrides/phones.json"), J("overrides/phone_sources.json"), J("overrides/phone_baseline.json")["listings"]
        holds = J("overrides/phone_holds.json")
        shown = phone_rule.phones_to_apply(ph, src, holds)
        for i, n in NEW.items():
            self.assertEqual(ph[i], n, i); self.assertEqual(shown.get(i), n, i)
            self.assertEqual((dg(base[i]["phone"]), dg(base[i]["tel"])), (n, n), i)
            self.assertEqual(dg(src[i]["phone"]), n, i)
            self.assertEqual(src[i]["source"].rstrip("/"), "https://www.salvationarmy.org.uk/" + i.split("/", 1)[1], i)

    def test_each_logged_with_source_and_undo(self):
        L = [c for c in J("logs/listings_batch_28oct.json")["changes"] if c["kind"] == "phone" and "Salvation Army phones report 28 Oct" in c.get("note", "")]
        by = {c["id"]: c for c in L}
        self.assertEqual(set(by), set(NEW)); self.assertEqual(len(L), 32)
        our = {r["listing id"]: dg(r["our phone"]) for r in ROWS}
        for i, c in by.items():
            self.assertEqual(c["new"], NEW[i]); self.assertEqual(c["source"], "https://www.salvationarmy.org.uk/" + i.split("/", 1)[1])
            self.assertIn("same number on both reads", c["note"])
            self.assertEqual(dg(c["undo"]["set"]["phone"]), our[i], i)
            self.assertEqual(dg(c["undo"]["set"]["tel"]), our[i], i)
        named = {r["listing id"] for r in ROWS if r["number_type"] == "named person's mobile"}
        for i in named: self.assertIn("named person's number is OK if the organisation's own page publishes it", by[i]["note"])

    def test_unclear_rows_untouched(self):
        d, ph = layer("data.full.js"), J("overrides/phones.json")
        base = J("overrides/phone_baseline.json")["listings"]
        L = J("logs/listings_batch_28oct.json")["changes"]
        for i, n in UNCLEAR.items():
            self.assertEqual(dg(d[i]["phone"]), n, i); self.assertNotIn(i, ph); self.assertEqual(dg(base[i]["phone"]), n, i)
            self.assertFalse([c for c in L if c["id"] == i and c["kind"] == "phone"], i)

if __name__ == "__main__": unittest.main()
