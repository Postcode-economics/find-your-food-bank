"""31 Oct 2026: 'Young people's housing (16-25), referral needed' is its own kind on the shelters layer.
Never an emergency bed: kept out of emergency / SWEP cards, own key line and badge in shelter blue.
Brighton and Hove Foyer is a town-level card (no map pin)."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import weather, build_seo as B

FID = "man-brighton-hove-foyer"
DC = ("man-connection-st-martins", "man-manna-day-centre", "man-sifa-fireside", "man-booth-centre",
      "man-whitechapel-centre", "man-peoples-kitchen-newcastle", "man-emmanuel-house-dropin",
      "man-lhm360-glasgow", "man-two-saints-day-centre")


def _r(n): return open(os.path.join(ROOT, n), encoding="utf-8").read()
def _items():
    t = _r("shelters.js"); return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}


class Kind(unittest.TestCase):
    def test_key_badge_and_welsh(self):
        L = _r("layers.js")
        self.assertIn("youth:'Young people’s housing (16–25), referral needed'", L)
        self.assertIn("youth:'Tai i bobl ifanc (16–25), angen atgyfeiriad'", L)
        self.assertIn("keyRow(symSvg('youth',20),'youth'", L)  # key line (flex row, data-t youth)
        self.assertIn("i.kind==='young_people'", L)
        self.assertIn('class="xkind xyouth"', L)  # card badge
        self.assertIn("if(i.no_pin)return;", L)  # town-level cards get no marker
        self.assertIn(".xkind.xyouth{border-color:#56B4E9", _r("layers.css"))
        self.assertIn("i.kind==='young_people'", _r("v3.js"))

    def test_never_emergency_or_swep(self):
        self.assertIn("c.kind==='young_people'", _r("emergency.js"))
        r = weather.card_from_source({"kind": "young_people", "official_council": True, "name": "X Foyer"}, None)
        self.assertEqual(r["publish"], "hold")
        self.assertIsNone(r["card"])

    def test_seo_card_label(self):
        h = B.card_sh({"kind": "young_people", "name": "F", "referral": "x"})
        self.assertIn("Young people’s housing (16–25), referral needed", h)
        self.assertNotIn(">Shelter<", h)

    def test_foyer_row(self):
        m = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))}[FID]
        self.assertEqual(m["kind"], "young_people")
        self.assertTrue(m["no_pin"])
        self.assertEqual(m["phone"], "01273 242700")
        self.assertIn("Housing Options", m["referral"])
        self.assertEqual(m["groups"], ["Young people 16-25"])

    def test_published(self):
        items = _items()
        self.assertEqual(items[FID]["kind"], "young_people")
        self.assertTrue(items[FID].get("no_pin"))
        for i in DC:
            self.assertEqual(items[i]["kind"], "day_centre", i)
            self.assertTrue(items[i]["phone"], i)


if __name__ == "__main__":
    unittest.main()
