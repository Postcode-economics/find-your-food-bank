import sys, os, tempfile, unittest, csv, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import monthly_counts as M
class T(unittest.TestCase):
    def test_rows(self):
        d = tempfile.mkdtemp(); open(os.path.join(d, "data.full.js"), "w").write("window.X=" + json.dumps({"items": [{"id": 1}, {"id": 2}]}) + ";")
        out = os.path.join(d, "m.csv")
        M.update(out, d, "2026-09"); M.update(out, d, "2026-10")
        open(os.path.join(d, "data.full.js"), "w").write("window.X=" + json.dumps({"items": [{"id": 1}]}) + ";"); M.update(out, d, "2026-10")
        r = list(csv.DictReader(open(out)))
        self.assertEqual([x["month"] for x in r], ["2026-09", "2026-10"]); self.assertEqual(r[0]["foodbanks"], "2"); self.assertEqual(r[1]["foodbanks"], "1"); self.assertEqual(r[1]["shelters"], "")
