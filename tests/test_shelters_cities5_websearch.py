"""1 Nov 2026: cities batch 5 WebSearch pass (Swindon, Gloucester, Cheltenham, Worcester, Telford,
Shrewsbury, Lincoln, Chester) - hand-verified shelters, day centres and young people's housing.
Phone found verbatim on each place's own page. Hermetic: no network."""
import json, os, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
OV = os.path.join(ROOT, "overrides")
NEW_IDS = [
    "man-swindon-foyer-stonewater",
    "man-p3-gloucester-accommodation-morroway-house",
    "man-daystop-gloucestershire-nightstop",
    "man-p3-cheltenham-accommodation",
    "man-maggs-day-centre-worcester",
    "man-kip-telford",
    "man-ymca-wellington-supported-housing",
    "man-ludlow-foyer-connexus",
    "man-nomad-centre-ymca-lincolnshire",
    "man-share-homeless-action-centre-chester",
]
TOWN_CARDS = {"man-p3-cheltenham-accommodation", "man-ymca-wellington-supported-housing"}


def _j(f):
    return json.load(open(os.path.join(OV, f), encoding="utf-8"))


class Cities5WebSearch(unittest.TestCase):
    def test_overrides(self):
        man = {x["id"]: x for x in _j("shelters_manual.json")}
        ver, app, base = _j("shelters_verified.json"), _j("approved_new_places.json")["shelters"], _j("phone_baseline.json")["listings"]
        for i in NEW_IDS:
            m = man[i]
            self.assertTrue(m["phone"] and m["lat"] and m["lng"], i)
            if i in TOWN_CARDS:
                # town-level card: never a referral/office postcode as location, never a pin
                self.assertTrue(m.get("no_pin"), i)
                self.assertEqual(m["postcode"], "", i)
                self.assertIn("exact address not published", m["address"], i)
            else:
                self.assertTrue(m["postcode"], i)
                self.assertFalse(m.get("no_pin"), i)
            self.assertIn(m["kind"], ("hostel", "day_centre", "young_people"), i)
            self.assertEqual(ver[i]["phone"], m["phone"], i)
            self.assertTrue(ver[i]["evidence_url"].startswith("http"), i)
            self.assertIn(i, app)
            self.assertEqual(base[i]["phone"], m["phone"], i)
            if isinstance(m["facilities"], list):
                self.assertTrue(m["facilities"] and m.get("facilities_quote"), i)
            else:
                self.assertEqual(m["facilities"], "Not stated", i)
            if m["groups"]:
                self.assertTrue(m.get("groups_quote"), i)
            self.assertEqual(m["who_for"], m["groups"] or "Not stated", i)
            self.assertNotIn("Women only", m["groups"], i)
            if m["kind"] == "young_people":
                self.assertIn("Young people 16-25", m["groups"], i)
                self.assertIn("Referral needed", m["referral"], i)
            if m["kind"] == "day_centre":
                self.assertEqual(m["season"], "Daytime only", i)
                self.assertEqual(m["beds"], "", i)

    def test_stale_nomad_trust_not_added(self):
        # nomadtrust.org.uk still shows the Monks Road shelter, replaced in Nov 2019 by the YMCA Nomad Centre
        man = _j("shelters_manual.json")
        self.assertFalse([x for x in man if "LN2 5HL" in (x.get("postcode") or "")])


if __name__ == "__main__":
    unittest.main()
