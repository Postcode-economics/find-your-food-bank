"""31 Oct 2026: BHT Phase One (Brighton) hand-verified hostel, council referral line as phone."""
import json, os, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
OV = os.path.join(ROOT, "overrides")
ID = "man-bht-phase-one"
REF = "Referral only: ask Brighton & Hove Council's housing team (Supported Accommodation Panel). You need a local connection."


def _j(name):
    return json.load(open(os.path.join(OV, name), encoding="utf-8"))


class BhtPhaseOne(unittest.TestCase):
    def test_manual_row(self):
        m = {x["id"]: x for x in _j("shelters_manual.json")}[ID]
        self.assertEqual(m["name"], "BHT Phase One")
        self.assertEqual(m["postcode"], "BN1 2LL")
        self.assertEqual(m["kind"], "hostel")
        self.assertEqual(m["phone"], "01273 294400")
        self.assertEqual(m["referral"], REF)
        self.assertEqual(m["access_type"], "referral_only")
        self.assertAlmostEqual(m["lat"], 50.823, places=2)
        self.assertAlmostEqual(m["lng"], -0.154, places=2)

    def test_verified_quotes(self):
        v = _j("shelters_verified.json")[ID]
        self.assertIn("Supported Accommodation Panel", v["quote"])
        self.assertIn("29-32 Oriental Place", v["quote"])
        self.assertIn("01273 29 44 00", v["phone_quote"])
        self.assertTrue(v["phone_source"].startswith("https://www.brighton-hove.gov.uk/"))

    def test_approved_and_baseline(self):
        self.assertIn(ID, _j("approved_new_places.json")["shelters"])
        b = _j("phone_baseline.json")["listings"][ID]
        self.assertEqual((b["layer"], b["tel"]), ("shelters", "01273294400"))

    def test_published(self):
        t = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
        items = {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}
        self.assertIn(ID, items)
        self.assertEqual(items[ID]["phone"], "01273 294400")


if __name__ == "__main__":
    unittest.main()
