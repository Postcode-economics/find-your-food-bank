"""Old PRs #228, #231, #233 and #234 closed on 1 Nov 2026 (Dean approved). Only the parts still needed on current main
were redone, each re-read on the place's own page on 1 Nov 2026 and quoted. This locks them so a refresh can't drop them."""
import json, os, re, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def load(rel):
    with open(os.path.join(R, rel), encoding="utf-8") as f:
        return json.load(f)


def listing(rel):
    s = open(os.path.join(R, rel), encoding="utf-8").read()
    return {i["id"]: i for i in json.loads(s[s.index("{"):s.rstrip().rstrip(";").rindex("}") + 1])["items"]}


TIMES = {  # id: (structured, words that must be in the quote)
    "pontypridd": ({"tue": [["09:00", "13:45"]], "wed": [["09:00", "13:45"]], "thu": [["09:00", "13:45"]], "fri": [["09:00", "13:45"]], "sat": [["10:00", "11:45"]]}, "CF37 1BW"),
    "rickmansworth/mill-end": ({"tue": [["13:45", "16:00"]], "fri": [["10:00", "12:00"]]}, "WD3 7HJ"),
    "thurrock/all-saints-church-south-ockendon": ({"thu": [["11:00", "13:00"]]}, "RM15 5HF"),
    "thurrock/gates-of-praise-international-christian-centre": ({"sat": [["10:00", "12:00"]]}, "RM17 5YF"),
    "thurrock/gateway-peoples-centre": ({"wed": [["11:00", "13:00"]]}, "SS17 0EY"),
    "thurrock/st-francis-centre-linford": ({"thu": [["11:00", "13:00"]]}, "SS17 0QA"),
    "thurrock/st-john-the-baptist-church-tilbury": ({"tue": [["11:00", "13:00"]]}, "RM18 7PP"),
    "thurrock/st-stephens-church-hall-purfleet": ({"fri": [["10:00", "12:00"]]}, "RM19 1QD"),
    "wirral/st-james-church-new-brighton": ({"thu": [["10:30", "12:30"]]}, "CH45 9LF"),
    "wirral/st-joseph-and-st-albans": ({"tue": [["17:30", "19:00"]]}, "CH44 5UD"),
    # Woking's own card no longer lists the Thursday 17:30-18:30 session old PR #228 had.
    "woking": ({"mon": [["10:30", "12:30"]], "wed": [["10:30", "12:30"]], "thu": [["10:30", "12:30"]]}, "GU21 6EL"),
    "silklife": ({"tue": [["09:30", "11:30"]], "fri": [["09:30", "11:30"]]}, "9:30am and 11:30am"),
    "trinity": ({"fri": [["09:00", "12:00"]]}, "Friday 9 - 12"),
    "poole/st-gabriels-church-hall": ({"tue": [["13:30", "15:00"]]}, "BH16 5BH"),
    "poole/st-clements-church-hall": ({d: [["11:00", "12:30"]] for d in ("mon", "tue", "wed", "thu", "fri")}, "BH15 3PH"),
    "westminster": ({"mon": [["13:00", "15:00"]], "thu": [["11:00", "13:00"]]}, "Client sessions"),
}
TEXT_ONLY = ["bradford-north", "broxbourne", "fusion/calderdale", "redcar-area", "ringwood", "salford", "thame",
             "patch", "newark/tuxford", "salvation-army/hastings-temple", "somebody-cares"]
HELD = ["edinburgh-food-project/clermiston", "salvation-army/inverness", "sadaka", "skegness", "wokingham",
        "wansbeck-valley/ymca", "tameside-south-longdendale", "rickmansworth/maple-cross"]


class FoodBankTimes(unittest.TestCase):
    def setUp(self):
        self.ot = load("overrides/opening_times.json")

    def test_redone_times_are_protected_and_quoted(self):
        for k, (st, words) in TIMES.items():
            e = self.ot[k]
            self.assertEqual(e["structured"], st, k)
            self.assertEqual(e["status"], "TIMES_FOUND", k)
            self.assertTrue(e.get("protected"), k)
            self.assertTrue(e["reader"].startswith("hand-reviewed 2026-11-01"), k)
            self.assertEqual(e["checked_date"], "2026-11-01", k)
            self.assertIn(words, " ".join(e["quote"]), k)

    def test_labelled_text_only_is_not_a_collection_table(self):
        for k in TEXT_ONLY:
            e = self.ot[k]
            self.assertEqual(e["status"], "TIMES_TEXT_ONLY", k)
            self.assertIsNone(e["structured"], k)
            self.assertTrue(e.get("quote") and e["quote"][0], k)

    def test_every_redone_entry_has_a_quote_and_own_page(self):
        n = 0
        for k, e in self.ot.items():
            if "redone on current main 1 Nov 2026" in str(e.get("reader", "")):
                n += 1
                self.assertTrue(e.get("source_url", "").startswith("http"), k)
                self.assertTrue(all(q.strip() for q in e["quote"]), k)
                self.assertNotEqual(e["status"], "NO_TIMES", k)  # nothing removed or closed in this PR
        self.assertEqual(n, 64)

    def test_doubtful_items_were_held_not_changed(self):
        for k in HELD:
            self.assertNotIn("redone on current main 1 Nov 2026", str(self.ot.get(k, {}).get("reader", "")), k)

    def test_notices_match_their_redone_times(self):
        notices = load("overrides/foodbank_notices.json")
        for k in ("redcar-area", "ringwood", "salford", "broxbourne", "newark/tuxford", "thame"):
            self.assertEqual(notices[k]["set"], "2026-11-01", k)
            self.assertIn("redone on current main", self.ot[k]["reader"], k)


class Shelters(unittest.TestCase):
    def test_independence_house_address_and_nightsafe_hours(self):
        v = load("overrides/shelters_verified.json")
        self.assertEqual(v["osm-way-1125252517"]["address"], "235 Barmouth Street, Beswick, Manchester")
        self.assertIn("235 Barmouth Street Beswick Manchester M11 3TB", v["osm-way-1125252517"]["address_quote"])
        h = v["hl-nightsafe-blackburn"]["hours"]
        self.assertEqual(set(h), {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"})
        self.assertEqual(set(h.values()), {"17:00 - 10:00"})
        self.assertIn("365 days - from 5.00 pm to 10.00 am", v["hl-nightsafe-blackburn"]["hours_quote"])

    def test_verified_hours_and_address_reach_the_listing(self):
        import sys
        sys.path.insert(0, os.path.join(R, "scripts"))
        import common, tempfile
        pend = os.path.join(tempfile.mkdtemp(), "pending.json")
        v = load("overrides/shelters_verified.json")
        x = {"id": "hl-nightsafe-blackburn", "name": "n", "hours": {"Mon": "10:00 - 16:00"}, "address": "a", "postcode": "BB1 1EZ"}
        y = {"id": "osm-way-1125252517", "name": "i", "address": "120 Barmouth Street", "postcode": "M11 3TB"}
        out = common.verification_gate([x, y], [], v, "2026-11-01", pend, recheck=False)[0]
        got = {i["id"]: i for i in out}
        self.assertEqual(got["hl-nightsafe-blackburn"]["hours"]["Sun"], "17:00 - 10:00")
        self.assertEqual(got["osm-way-1125252517"]["address"], "235 Barmouth Street, Beswick, Manchester")


class WarmSpaces(unittest.TestCase):
    def test_address_fixes(self):
        fx = {f["id"]: f for f in load("overrides/warmspaces_fixes.json")}
        for k in ("ww-68911571", "ww-55474670", "ww-65437345"):  # postcode no longer repeated
            pc = fx[k]["postcode"]
            self.assertEqual(fx[k]["address"].count(pc), 1, k)
            self.assertNotIn(pc.split()[1] + " " + pc.split()[1], fx[k]["address"], k)
        self.assertIn("Baildon, Shipley", fx["ww-68524251"]["address"])
        self.assertIn("172 Belsize Road", fx["ww-55472884"]["address"])
        self.assertIn("Lockleaze", fx["ww-65438865"]["address"])
        self.assertIn("2 Station Grove", fx["ww-65070433"]["address"])
        for f in fx.values():
            if "redone from old PR #234" in f.get("reason", ""):
                self.assertNotIn("lat", f)
                self.assertNotIn("lng", f)  # no pin moved

    def test_verified_hours(self):
        v = load("overrides/warmspaces_verified.json")
        self.assertEqual(v["ww-68896770"]["hours"]["Fri"], "11:00 - 15:00")
        self.assertEqual(v["ww-63065216"]["hours"], {"Thu": "14:00 - 16:00 Fortnightly"})
        self.assertNotIn("Tue", v["ww-64379462"]["hours"])
        self.assertEqual(v["ww-64379462"]["hours"]["Sat"], "10:00 - 13:00")

    def test_phone_fixes_keep_the_lock_and_the_listing_together(self):
        base = load("overrides/phone_baseline.json")["listings"]
        live = listing("warmspaces.js")
        for k, phone in (("ww-55473520", "01606 42943"), ("ww-57951889", "07876 372274")):
            self.assertEqual(base[k]["phone"], phone, k)
            self.assertEqual(live[k]["phone"], phone, k)
            self.assertEqual(base[k]["tel"], re.sub(r"\D", "", phone), k)


if __name__ == "__main__":
    unittest.main()
