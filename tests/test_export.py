import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import export_data as e
class T(unittest.TestCase):
    def test_osm_excluded(self):
        self.assertFalse(e.shareable_shelter({"source": "OpenStreetMap"})); self.assertTrue(e.shareable_shelter({"source": "Operator website"}))
    def test_no_private_fields(self):
        for f in ("email", "notes", "opening_times", "hours", "fb_page"): self.assertNotIn(f, e.FB + e.SH + e.WS)

import csv, json
ROOT = os.path.join(os.path.dirname(__file__), "..")
def _items(f):
    s = open(os.path.join(ROOT, f), encoding="utf-8").read()
    if f != "data.js": return {i["id"]: i for i in json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", [])}
    c = json.loads(s[s.rindex("})(") + 3: s.rindex(");")].rstrip(")"))  # compact columns, decoded as data.js's own loader does
    out = {}
    for n in range(c["n"]):
        o = {k: c["c"][k][n] for k in ("id", "postcode", "address") if n < len(c["c"][k]) and c["c"][k][n] not in (None, "~")}
        if str(o.get("address", "")).endswith("\u00a7"): o["address"] = o["address"][:-1] + ", " + o.get("postcode", "")
        out[o["id"]] = o
    return out
class ExportsMatchData(unittest.TestCase):
    """Committed export/ files must agree with the map data (stale exports once undid main's Cardiff address fix, 115f29638)."""
    def _check(self, rows, data, src):
        bad = [(r["id"], r["address"], r["postcode"], data[r["id"]].get("address", ""), data[r["id"]].get("postcode", ""))
               for r in rows if r["id"] in data and (r["address"] != (data[r["id"]].get("address") or "") or r["postcode"] != (data[r["id"]].get("postcode") or ""))]
        self.assertEqual(bad, [], "export/foodbanks out of date vs %s - run python scripts/export_data.py" % src)
    def test_csv_and_json_match_data_js(self):
        csv_rows = list(csv.DictReader(open(os.path.join(ROOT, "export", "foodbanks.csv"), encoding="utf-8")))
        json_rows = json.load(open(os.path.join(ROOT, "export", "foodbanks.json"), encoding="utf-8"))["items"]
        for src in ("data.js", "data.full.js"):
            d = _items(src); self.assertGreater(len(d), 1000)
            self._check(csv_rows, d, src); self._check(json_rows, d, src)
        self.assertEqual({r["id"] for r in csv_rows}, set(_items("data.full.js")))
    def test_cardiff_addresses(self):
        rows = {r["id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "export", "foodbanks.csv"), encoding="utf-8"))}
        self.assertEqual(rows["cardiff/central"]["postcode"], "CF11 6LU"); self.assertIn("3 Lower Cathedral Road", rows["cardiff/central"]["address"])
        self.assertEqual(rows["cardiff/tongwynlais"]["postcode"], "CF15 7NS")
