"""Labels per owner 21 Oct 2026 (commit 2ededef): 'Food bank – get food here' on the map, 'Donations only' on non-client
sites, B30 locked wording untouched; classify.py must keep them on every rebuild."""
import sys, os, json, unittest, re
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import classify as C
class T(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((C.EN, C.CY, C.DROP_EN, C.DROP_CY), ("Donations only", "Rhoddion yn unig", "Donations only", "Rhoddion yn unig"))
    def test_render_label(self):
        h = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn(">Food bank<", h)  # owner 24 Oct new look: exact mockup wording; self.assertNotIn("collect food here", h); self.assertNotIn("drop off food only", h)
    def test_b30_locked(self):
        m = json.load(open(os.path.join(ROOT, "overrides", "foodbank_manual.json")))
        self.assertTrue(m["b30-south-birmingham"]["locked"])
    def test_rebuild_keeps_labels(self):
        t = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read(); items = json.loads(t[t.index("=") + 1:].strip().rstrip(";"))["items"]
        C.classify(items, ROOT)
        labs = {(i.get("label_en"), i.get("label_cy")) for i in items if i.get("label_en")}
        b30 = [i for i in items if i["id"] == "b30-south-birmingham"]
        other = labs - {(b30[0].get("label_en"), b30[0].get("label_cy"))} if b30 else labs
        self.assertEqual(other, {("Donations only", "Rhoddion yn unig")})
        if b30: self.assertTrue(b30[0]["label_en"].startswith("Warehouse – donations only"))
if __name__ == "__main__": unittest.main()
