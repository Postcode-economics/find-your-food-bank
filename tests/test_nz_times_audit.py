"""N-Z times audit (27 Oct 2026): 13 listings re-checked by hand on each organisation's own site.
Each hand-reviewed protected override must hold in the override file, data.full.js, data.js and its area page."""
import os, sys, json, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from times import normalise
def S(**k): return {d: [list(p) for p in v] for d, v in k.items()}
T = ("11:00", "13:00")
WANT = {  # id: (structured, area page, wrong slot that must be gone)
    "rickmansworth/mill-end": (S(tue=[("13:45", "16:00")], fri=[("10:00", "12:00")]), "three-rivers", "12:15"),
    "trinity": (S(fri=[("09:00", "12:00")]), "bury", "14:00"),
    "silklife": (S(tue=[("09:30", "11:30")], fri=[("09:30", "11:30")]), "cheshire-east", "12:30"),
    "thurrock/st-francis-centre-linford": (S(thu=[T]), "thurrock", "15:00"),
    "thurrock/st-stephens-church-hall-purfleet": (S(fri=[("10:00", "12:00")]), "thurrock", "16:00"),
    "thurrock/all-saints-church-south-ockendon": (S(thu=[T]), "thurrock", "fri"),
    "thurrock/gateway-peoples-centre": (S(wed=[T]), "thurrock", "thu"),
    "thurrock/st-john-the-baptist-church-tilbury": (S(tue=[T]), "thurrock", "wed"),
    "thurrock/gates-of-praise-international-christian-centre": (S(sat=[("10:00", "12:00")]), "thurrock", "09:30"),
    "wirral/st-joseph-and-st-albans": (S(tue=[("17:30", "19:00")]), "wirral", "12:30"),
    "wirral/st-james-church-new-brighton": (S(thu=[("10:30", "12:30")]), "wirral", "14:30"),
    "woking": (S(mon=[("10:30", "12:30")], wed=[("10:30", "12:30")], thu=[("10:30", "12:30"), ("17:30", "18:30")]), "woking", "16:00"),
    "pontypridd": (S(tue=[("09:00", "13:45")], wed=[("09:00", "13:45")], thu=[("09:00", "13:45")], fri=[("09:00", "13:45")], sat=[("10:00", "11:45")]), "rhondda-cynon-taf", "13:00"),
}
OT = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
_s = open(os.path.join(ROOT, "data.full.js")).read()
FULL = {i["id"]: i for i in json.loads(_s[_s.find("{"):_s.rfind("}") + 1])["items"]}
_c = open(os.path.join(ROOT, "data.js")).read().rstrip().rstrip(";")
C = json.loads(_c[_c.find("})(") + 3:-1])["c"]
def wrong_absent(t, want, bad):
    st = t["structured"]
    if bad in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"): return bad not in st
    return bad not in json.dumps(st)
def make(k, want, area, bad):
    def t_override(self):
        o = OT[k]; self.assertEqual(o["status"], "TIMES_FOUND"); self.assertEqual(o["structured"], want)
        self.assertTrue(o["reader"].startswith("hand-reviewed")); self.assertEqual(normalise(o)["structured"], want)
    def t_data(self):
        for ot in (FULL[k]["opening_times"], C["opening_times"][C["id"].index(k)]):
            self.assertEqual(ot["structured"], want); self.assertTrue(wrong_absent(ot, want, bad))
    def t_area(self):
        import html as H
        h = open(os.path.join(ROOT, "food-banks", area, "index.html")).read()
        i = h.find(H.escape(FULL[k]["name"]) + "</div>"); self.assertGreater(i, 0)
        card = h[i:h.find("</li>", i)]
        for d, v in want.items():
            self.assertIn("<td>%s</td><td>%s</td>" % (d.title(), ", ".join("%s\u2013%s" % tuple(p) for p in v)), card)
    return type("T_" + re.sub(r"\W", "_", k), (unittest.TestCase,), {"test_override": t_override, "test_data_files": t_data, "test_area_page_lists_it": t_area})
for _k, (_w, _a, _b) in WANT.items(): globals()["T_" + re.sub(r"\W", "_", _k)] = make(_k, _w, _a, _b)
if __name__ == "__main__": unittest.main()
