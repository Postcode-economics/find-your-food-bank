"""Warm space duplicates (14 Nov 2026): reviewed merges fill the kept card and never lose a place;
the automatic check only records likely duplicates (rule 104, shadow first)."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import warmspaces_dedupe as D


def card(i, name, **kw):
    x = dict(id=i, name=name, address=kw.pop("address", name + ", Town AB1 2CD"), postcode=kw.pop("postcode", "AB1 2CD"),
             lat=kw.pop("lat", 50.8), lng=kw.pop("lng", -0.5), phone=kw.pop("phone", "01903 111111"),
             hours=kw.pop("hours", {"Thu": "10:00 - 12:00"}), provided=kw.pop("provided", []))
    x.update(kw)
    return x


class ApplyReviewed(unittest.TestCase):
    def test_fills_blanks_and_combines_facilities_only(self):
        keep = card("ww-1", "Hall", website="", provided=["Hot Drinks"], notes="")
        twin = card("ww-2", "Hall copy", phone="01234 999999", website="https://hall.example.org/",
                    provided=["Hot Drinks", "Free Wifi"], notes="Board games", address="Elsewhere", lat=51.0, lng=-1.0)
        rows = [{"id": "ww-2", "duplicate_of": "ww-1", "reason": "test"}]
        drop, log = D.apply_reviewed([keep, twin], rows)
        self.assertEqual(drop, {"ww-2"})
        self.assertEqual(keep["website"], "https://hall.example.org/")
        self.assertEqual(keep["notes"], "Board games")
        self.assertEqual(keep["provided"], ["Hot Drinks", "Free Wifi"])
        # never copied: phone, name, address, pin
        self.assertEqual(keep["phone"], "01903 111111")
        self.assertEqual(keep["name"], "Hall")
        self.assertEqual(keep["address"], "Hall, Town AB1 2CD")
        self.assertEqual((keep["lat"], keep["lng"]), (50.8, -0.5))
        self.assertEqual(log[0]["result"], "merged")

    def test_kept_hours_are_not_replaced(self):
        keep = card("ww-1", "Hall", hours={"Tue": "10:00 - 14:00"})
        twin = card("ww-2", "Hall", hours={"Tue": "10:00 - 12:30"})
        D.apply_reviewed([keep, twin], [{"id": "ww-2", "duplicate_of": "ww-1"}])
        self.assertEqual(keep["hours"], {"Tue": "10:00 - 14:00"})

    def test_warm_welcome_link_gives_way_to_own_site(self):
        keep = card("ww-1", "Hall", website="https://www.warmwelcome.uk/find-a-space")
        twin = card("ww-2", "Hall", website="https://hall.example.org/")
        D.apply_reviewed([keep, twin], [{"id": "ww-2", "duplicate_of": "ww-1"}])
        self.assertEqual(keep["website"], "https://hall.example.org/")

    def test_hand_made_kept_card_is_left_unchanged(self):
        keep = card("sw-1", "Church", website="https://council.example.gov.uk/", provided=[])
        before = json.dumps(keep, sort_keys=True)
        twin = card("ww-2", "Church", website="https://church.example.org/", provided=["Free Wifi"])
        drop, log = D.apply_reviewed([keep, twin], [{"id": "ww-2", "duplicate_of": "sw-1"}], hand_ids={"sw-1"})
        self.assertEqual(drop, {"ww-2"})
        self.assertEqual(json.dumps(keep, sort_keys=True), before)

    def test_twin_stays_when_kept_card_is_missing(self):
        twin = card("ww-2", "Hall")
        drop, log = D.apply_reviewed([twin], [{"id": "ww-2", "duplicate_of": "ww-1"}])
        self.assertEqual(drop, set())
        self.assertIn("kept", log[0]["result"])

    def test_plain_exclusions_are_not_merges(self):
        self.assertEqual(D.reviewed_rows([{"id": "ww-9", "reason": "closed"}, {"id": "ww-8", "duplicate_of": "ww-8"}]), {})


class Find(unittest.TestCase):
    def kinds(self, items, **kw):
        return {(p["a"], p["b"]): p["kind"] for p in D.find(items, **kw)}

    def test_same_space_page_under_two_ids(self):
        a = card("ww-1", "Wembley Library", source_url="https://www.warmwelcome.uk/space?l=23064")
        b = card("ww-2", "Wembley Library", source_url="https://www.warmwelcome.uk/space?l=23064", lat=50.81)
        self.assertEqual(self.kinds([a, b]), {("ww-1", "ww-2"): "certain"})

    def test_misspelt_copy_same_phone_and_sessions(self):
        a = card("n-1", "Willowburn Sports and Leisure Centre")
        b = card("n-2", "Willowbrun Sports and Leisure Centre")
        self.assertEqual(self.kinds([a, b]), {("n-1", "n-2"): "certain"})

    def test_different_sessions_are_only_possible(self):
        a = card("ww-1", "Ikhlas Community Centre", hours={"Wed": "10:00 - 12:00"})
        b = card("ww-2", "Ikhlas Education Centre", hours={"Mon": "12:00 - 14:00", "Wed": "13:00 - 14:00"})
        self.assertEqual(self.kinds([a, b]), {("ww-1", "ww-2"): "possible"})

    def test_same_address_different_name_is_possible(self):
        # e.g. one leisure centre's card carrying another centre's address
        a = card("ww-1", "Littlehampton Wave", address="Littlehampton Wave, Littlehampton BN16 2NA", postcode="BN16 2NA")
        b = card("ww-2", "Arun Leisure Centre", address="Littlehampton Wave, Littlehampton BN16 2NA", postcode="BN16 2NA",
                 phone="01243 826612", hours={"Mon": "12:00 - 14:00"})
        self.assertEqual(self.kinds([a, b]), {("ww-1", "ww-2"): "possible"})

    def test_different_places_are_not_listed(self):
        a = card("ww-1", "Clitheroe Library", postcode="BB7 2DG", phone="0300 123 6703")
        b = card("ww-2", "Clitheroe United Reformed Church", postcode="BB7 1AZ", phone="07935 465204", lat=50.802)
        self.assertEqual(self.kinds([a, b]), {})

    def test_reviewed_twins_are_skipped(self):
        a = card("ww-1", "Hall"); b = card("ww-2", "Hall")
        self.assertEqual(self.kinds([a, b], reviewed={"ww-2"}), {})

    def test_find_never_changes_cards(self):
        a = card("ww-1", "Hall"); b = card("ww-2", "Hall")
        before = json.dumps([a, b], sort_keys=True)
        D.find([a, b])
        self.assertEqual(json.dumps([a, b], sort_keys=True), before)


class ReviewedList(unittest.TestCase):
    def test_reviewed_duplicates_are_sound(self):
        with open(os.path.join(ROOT, "overrides", "warmspaces_exclude.json"), encoding="utf-8") as f:
            rows = json.load(f)
        ids = {r["id"] for r in rows}
        pairs = D.reviewed_rows(rows)
        self.assertTrue(pairs)
        for loser, winner in pairs.items():
            self.assertNotEqual(loser, winner)
            self.assertNotIn(winner, ids, "%s is kept for %s but is itself left off" % (winner, loser))
        for r in rows:
            if r.get("duplicate_of"):
                self.assertTrue(r.get("exact"), r["id"])
                self.assertTrue(r.get("reason"), r["id"])
        with open(os.path.join(ROOT, "overrides", "warmspaces_manual.json"), encoding="utf-8") as f:
            man = {m.get("id") for m in json.load(f) if isinstance(m, dict)}
        self.assertFalse(set(pairs) & man, "a hand-made card is never the one left off")


class BuildWiring(unittest.TestCase):
    def test_build_merges_before_exclusion_and_check_is_record_only(self):
        src = open(os.path.join(ROOT, "scripts", "build_warmspaces.py"), encoding="utf-8").read()
        i_apply = src.index("warmspaces_dedupe.apply_reviewed(")
        i_excl = src.index("items = [x for x in items if x[\"id\"] not in EXCL]")
        self.assertLess(i_apply, i_excl)
        self.assertIn("- _DUP_KEEP", src)
        i_find = src.index("warmspaces_dedupe.find(")
        block = src[i_find:src.index("import shelter_contacts", i_find)]
        self.assertNotIn("items =", block, "the duplicate check must not change the list")


if __name__ == "__main__":
    unittest.main()
