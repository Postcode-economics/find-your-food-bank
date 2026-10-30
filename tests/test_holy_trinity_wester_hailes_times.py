"""Holy Trinity Wester Hailes (ifan-5b9fd1318a04132921a389-0): Play Café Monday nav hours were auto-applied as food bank times.

Hand-checked override: food bank is Tuesday 2pm walk-in (text only). Known skip stops the finder re-using Play Café hours."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, times_finder as TF

FX = os.path.join(os.path.dirname(__file__), "fixtures", "holy_trinity_wester_hailes_contact_2026-10-30.html")
KID = "ifan-5b9fd1318a04132921a389-0"
ITEM = {"id": KID, "name": "Holy Trinity Church, Wester Hailes", "postcode": "EH14 2SL",
        "website": "https://www.holytrinitywesterhailes.org.uk"}
RAW = "Tuesdays from 2pm, no appointment needed"
URL = "https://holytrinitywesterhailes.org.uk/contact-supporting-wh/"
QUOTE = ("For our Foodbank, no appointments are needed. You can just come on a Tuesday at 2.00pm "
         "and we'll be happy to speak about any help you need.")
SKIP = "Play Café Monday hours from the site nav/sidebar"


def items():
    s = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]}


class HolyTrinityWesterHailes(unittest.TestCase):
    def setUp(self):
        self.html = open(FX, encoding="utf-8").read()
        self.ot = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json")))
        self.ks = TF.known()

    def test_page_carries_play_cafe_nav_and_foodbank_walk_in(self):
        text = TF.fix_text(self.html)
        self.assertIn("Play Café – Mondays at 9.30am – 11.00am", text)
        self.assertIn("For our Foodbank, no appointments are needed", text)
        self.assertIn("Tuesday at 2.00pm", text)

    def test_finder_reading_is_monday_play_cafe_not_food_bank(self):
        orig = TF.polite
        self.addCleanup(setattr, TF, "polite", orig)
        TF.polite = lambda u, tries=3: (200, u, self.html) if "holytrinity" in u else orig(u, tries)
        found = TF.run([dict(ITEM)], threads=1)["found"][KID]
        self.assertEqual(found["structured"], {"mon": [["09:30", "11:00"]]})
        self.assertNotIn("tue", (found.get("structured") or {}))

    def test_known_skip_blocks_auto_apply(self):
        self.assertIn(SKIP, TF.skipped(KID, self.ks))
        found = {"raw": "Mondays 9.30am – 11.00am", "status": "TIMES_FOUND",
                 "structured": {"mon": [["09:30", "11:00"]]}, "source_url": URL, "fb_mention": True, "reader": "times_finder"}
        why = TF.strict_checks(KID, found, ITEM, self.ot, {}, 2, self.ks, {}, {})
        self.assertTrue(any("known skip" in w and SKIP.split()[0] in w for w in why), why)
        self.assertTrue(any("protected" in w for w in why), why)

    def test_protected_text_only_on_map(self):
        e = self.ot[KID]
        self.assertTrue(e["protected"] and e["status"] == "TIMES_TEXT_ONLY" and e["structured"] is None)
        self.assertEqual(e["raw"], RAW)
        self.assertEqual(e["source_url"], URL)
        self.assertIn("Tuesday at 2.00pm", e["quote"][0])
        card = items()[KID]["opening_times"]
        self.assertEqual(card["raw"], RAW)
        self.assertEqual(card["lines"], [RAW])
        self.assertIsNone(card.get("structured"))
        self.assertNotIn("mon", json.dumps(card))
        self.assertEqual(items()[KID]["times_status"], "confirmed_by_hand")

    def test_refresh_treats_as_hand_checked(self):
        ix = items()[KID]
        self.assertTrue(D.hand_checked(ix, "opening_times"))
        why = TF.strict_checks(KID, {"raw": "Mondays 9.30am – 11.00am", "source_url": URL}, ix, self.ot, {}, 1, self.ks, {}, {})
        self.assertIn("hand-checked times are protected; finder only flags differences", why)


if __name__ == "__main__":
    unittest.main()
