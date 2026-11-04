"""Dean 4 Nov 2026: 'advice_service' is its own shelters-layer kind ('Advice service': advice and housing help,
no beds, food or drop-in). Crisis Skylight Oxford uses it, so it never reads as a drop-in day centre or a bed."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import weather, build_seo as B

FID = "man-crisis-skylight-oxford"
LINE = "Advice and housing help. No beds, food or drop-in."
def _r(n): return open(os.path.join(ROOT, n), encoding="utf-8").read()

class AdviceService(unittest.TestCase):
    def test_label_line_icon_key_and_welsh(self):
        L = _r("layers.js")
        self.assertIn("adviceService:'Advice service'", L)
        self.assertIn("adviceOnly:'%s'" % LINE, L)
        self.assertIn("adviceService:'Gwasanaeth cyngor'", L)
        self.assertIn("keyRow(symSvg('info',28),'adviceService','<small data-t=\"adviceOnly\"></small>')", L)
        self.assertIn("shAdvice(i)?'info'", L)  # own icon, never the day-centre sun or the hostel house
        self.assertIn("sk==='info'?'adviceService'", L)
        self.assertIn("const shHostel=i=>i&&!shDay(i)&&!shYouth(i)&&!shAdvice(i);", L)  # not under the hostel filter
        self.assertIn("i.kind==='advice_service'", _r("v3.js"))
        F = _r("facts.js")
        self.assertIn("return ['Advice service', 'Gwasanaeth cyngor']", F)
        self.assertIn("if (i.kind === 'severe_weather' || i.kind === 'advice_service') return false;", F)

    def test_never_emergency_swep_or_night_count(self):
        self.assertIn("c.kind==='advice_service'", _r("emergency.js"))
        r = weather.card_from_source({"kind": "advice_service", "official_council": True, "name": "X"}, None)
        self.assertEqual(r["publish"], "hold"); self.assertIsNone(r["card"])
        self.assertIn('"advice_service"', _r("scripts/city_watch.py"))

    def test_seo_card(self):
        h = B.card_sh({"kind": "advice_service", "name": "Crisis Skylight Oxford", "referral": "x"})
        self.assertIn(">Advice service<", h)
        self.assertIn(LINE, h)
        for bad in ("Day centre", "Daytime only", "Night shelter", ">Hostel<"):
            self.assertNotIn(bad, h)

    def test_crisis_oxford_record(self):
        m = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))}[FID]
        self.assertEqual(m["kind"], "advice_service")
        self.assertNotIn("drop-in", m["referral"].lower())
        self.assertNotIn("Engagement and Assessment", m["referral"])
        self.assertEqual(set(m["hours"]), {"Mon", "Tue", "Wed", "Thu", "Fri"})
        self.assertNotEqual(m.get("season"), "Daytime only")

if __name__ == "__main__":
    unittest.main()
