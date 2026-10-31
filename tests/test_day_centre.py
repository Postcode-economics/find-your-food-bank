"""Day centres sit on the shelters layer and must not look like an overnight bed."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_seo as B
import recheck as R
import weather

IDS = ("man-first-base-brighton", "man-clock-tower-sanctuary")
FB = "https://www.bht.org.uk/services/homelessness/first-base-day-centre/"
CTS = "https://www.thects.org.uk/get-help/the-day-centre/"


def shelters():
    text = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])["items"]


def by_id():
    return {i["id"]: i for i in shelters()}


class Label(unittest.TestCase):
    def test_welsh_and_english_label_and_no_tonight_on_a_day_centre_card(self):
        layers = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        v3 = open(os.path.join(ROOT, "v3.js"), encoding="utf-8").read()
        emergency = open(os.path.join(ROOT, "emergency.js"), encoding="utf-8").read()
        self.assertIn("dayCentre:'Day centre'", layers)
        self.assertIn("dayCentre:'Canolfan ddydd'", layers)
        self.assertIn("dayOnly:'Daytime only. No overnight bed.'", layers)
        self.assertIn("dayOnly:'Yn ystod y dydd yn unig. Dim gwely dros nos.'", layers)
        self.assertIn("dayFilt:'Day centres'", layers)
        self.assertIn("dayFilt:'Canolfannau dydd'", layers)
        self.assertIn('i.kind!==\'day_centre\'', layers.replace(" ", ""))
        self.assertIn("kind==='day_centre'", layers)
        self.assertIn("open tonight", v3)  # the guard is a replacement, not a new badge
        self.assertIn("i.kind==='day_centre'", v3)
        self.assertIn("c.kind==='day_centre'", emergency)
        self.assertNotIn("open tonight", layers.lower())

    def test_seo_card_shows_the_label_hours_and_offer_and_not_help_tonight(self):
        row = by_id()["man-first-base-brighton"]
        card = B.card_sh(row)
        self.assertIn("Day centre", card)
        self.assertIn("Daytime only. No overnight bed.", card)
        self.assertIn("09:00 - 10:30 / 11:00 - 12:30", card)
        self.assertIn("Offers:", card)
        self.assertNotIn("Help tonight", card)
        self.assertNotIn("open tonight", card.lower())
        self.assertNotIn(">Beds<", card)
        bare = B.card_sh(dict(row, tel="", phone=""))
        self.assertIn("No overnight bed.", bare)
        self.assertNotIn("Help tonight", bare)
        cts = B.card_sh(by_id()["man-clock-tower-sanctuary"])
        self.assertIn("10:30 - 13:30", cts)
        self.assertIn("Free hot lunch", cts)
        self.assertIn("Closed", cts)

    def test_not_an_emergency_or_swep_card(self):
        src = {"official_council": True, "name": "First Base Day Centre", "kind": "day_centre",
               "category": "swep", "swep_active": True, "added": "2026-10-31T12:00:00+00:00", "url": FB}
        held = weather.card_from_source(src, "2026-10-31T13:00:00+00:00")
        self.assertIsNone(held["card"])
        self.assertNotIn("swep_badge", held)
        self.assertEqual(held["publish"], "hold")


class Entries(unittest.TestCase):
    def test_both_verified_entries_publish_shape(self):
        rows = by_id()
        manual = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8"))}
        verified = json.load(open(os.path.join(ROOT, "overrides", "shelters_verified.json"), encoding="utf-8"))
        approved = json.load(open(os.path.join(ROOT, "overrides", "approved_new_places.json"), encoding="utf-8"))
        baseline = json.load(open(os.path.join(ROOT, "overrides", "phone_baseline.json"), encoding="utf-8"))["listings"]
        # Older approvals and a frozen number stay as they were.
        self.assertIn("man-hastings-wuth-night-shelter", approved["shelters"])
        self.assertEqual(baseline["man-hastings-wuth-night-shelter"]["phone"], "07367 060708")
        for i, url, tel in (
            ("man-first-base-brighton", FB, "01273326844"),
            ("man-clock-tower-sanctuary", CTS, "07884417146"),
        ):
            row, man, ver = rows[i], manual[i], verified[i]
            self.assertEqual(row["kind"], "day_centre")
            self.assertEqual(man["kind"], "day_centre")
            self.assertEqual(row["beds"], "")
            self.assertTrue(row["groups"])
            self.assertEqual(row["access_type"], "open_access")
            self.assertEqual(row["tel"], tel)
            self.assertEqual(baseline[i]["phone"], row["phone"])
            self.assertEqual(baseline[i]["tel"], tel)
            self.assertEqual(baseline[i]["layer"], "shelters")
            self.assertNotIn("council_phone", row)
            self.assertEqual(ver["evidence_url"], url)
            self.assertEqual(ver["verified_on"], "2026-10-31")
            self.assertIn(i, approved["shelters"])
            self.assertEqual(R.schema_errors(row, "sh"), [])
            self.assertNotIn("swep", json.dumps(row).lower())

    def test_own_page_quotes_still_match_the_evidence(self):
        """The sentences checked on each charity's own page on 31 Oct 2026."""
        verified = json.load(open(os.path.join(ROOT, "overrides", "shelters_verified.json"), encoding="utf-8"))
        pages = {
            "man-first-base-brighton": (
                "First Base Day Centre St Stephen's Hall Montpelier Place Brighton BN1 3BF 01273 326844 "
                "First Base is an open access day centre. We run two open access sessions each weekday morning "
                "from 9:00 – 10:30 and 11:00 – 12:30. No referral is required and anyone experiencing homelessness "
                "can come to these sessions for support and use of the facilities. " * 3
            ),
            "man-clock-tower-sanctuary": (
                "Clock Tower Sanctuary Wenlock House 41-43 North Street Brighton BN1 1RH "
                "Young people can access the centre 10.30am – 1:30pm on Monday, Tuesday, Thursday, Friday and Saturday. "
                "We are not open on Wednesdays or Sundays. A free hot lunch is available on Mondays, Tuesdays, Thursdays, "
                "Fridays, and Saturdays. aged 16-to-25. " * 3
            ),
        }
        for i, text in pages.items():
            row = by_id()[i]
            page = {"http": 200, "text": text, "final_url": verified[i]["evidence_url"], "etag": "", "last_modified": "", "sha256": "x"}
            result = R.check(row, verified[i], page, verified[i]["evidence_url"])
            self.assertTrue(result["ok"], (i, result))


if __name__ == "__main__":
    unittest.main()
