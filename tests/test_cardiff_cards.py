"""Cardiff Foodbank (27 Oct 2026): every centre showed Mon-Fri 09:30-13:30, the 'Our phone lines are monitored' line printed
on every Trussell centre card. Times must come from each centre's own card, matched by postcode or name. Parser only (data fix is a separate PR). Saved page:
tests/fixtures/cardiff_voucher_2026-10-27.html (scripts/styles stripped)."""
import os, sys, json, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D, trussell_times as T
PAGE = D.text_of(open(os.path.join(ROOT, "tests", "fixtures", "cardiff_voucher_2026-10-27.html")).read())
URL = "https://cardiff.foodbank.org.uk/emergency-food/i-have-a-food-voucher"
WANT = {"cathays": {"tue": [["13:00", "15:00"]], "sat": [["11:00", "13:00"]]}, "central": {"thu": [["10:00", "12:00"]]},
        "ely": {"mon": [["13:00", "15:00"]], "thu": [["13:00", "15:00"]]}, "grangetown": {"fri": [["12:00", "14:00"]]},
        "llanedeyrn": {"wed": [["13:00", "15:00"]], "fri": [["11:30", "13:30"]]},
        "splott": {"wed": [["13:00", "15:00"]], "thu": [["18:30", "20:00"]]}, "st-mellons": {"mon": [["12:30", "14:30"]]},
        "tongwynlais": {"wed": [["14:00", "16:00"]]}}
OLD_PC = {"cathays": "CF24 4ND", "central": "CF11 9AD", "ely": "CF5 4HX", "grangetown": "CF11 7HP", "llanedeyrn": "CF23 9UL",
          "splott": "CF24 2BW", "st-mellons": "CF3 0EH", "tongwynlais": "CF15 7LG"}
PHONE = {d: [["09:30", "13:30"]] for d in ("mon", "tue", "wed", "thu", "fri")}
class CardiffCards(unittest.TestCase):
    def test_parser_reads_each_card_not_phone_hours(self):
        cards = {c["name"]: c for c in T.parse_cards(PAGE)}
        self.assertEqual(len(cards), 8)
        for c in cards.values(): self.assertNotIn("09:30", c["raw"])
    def test_each_centre_matched_by_name_even_with_old_postcode(self):
        for k, pc in OLD_PC.items():
            name = k.replace("-", " ").title()
            st, new, why = D.card_check({"status": "TIMES_FOUND", "structured": PHONE}, [PAGE], {"id": "cardiff/" + k, "name": name, "postcode": pc}, "2026-10-27", URL)
            self.assertEqual(st, "changed", k); self.assertEqual(new["structured"], WANT[k], k)
            st2, _, _ = D.card_check(new, [PAGE], {"id": "cardiff/" + k, "name": name, "postcode": pc}, "2026-10-27", URL)
            self.assertEqual(st2, "confirmed", k)
    def test_phone_hours_never_confirmed_from_page(self):
        st, _, _ = D.confirm_times({"status": "TIMES_FOUND", "structured": PHONE}, [PAGE])
        self.assertNotEqual(st, "confirmed")
        self.assertIsNone(D.extract_times("Our phone lines are monitored Monday - Friday 09:30-13:30", None))
    def test_ely_does_not_take_centrals_thursday(self):
        st, new, _ = D.card_check({"status": "TIMES_TEXT_ONLY", "raw": "Thursday 10:00 am to 12:00 pm | Monday - Friday 09:30-13:30", "structured": None},
                                  [PAGE], {"id": "cardiff/ely", "name": "Ely", "postcode": "CF5 4HX"}, "2026-10-27", URL)
        self.assertEqual(new["structured"], WANT["ely"])
    def test_warehouse_is_not_a_collection_point(self):
        st, new, _ = D.card_check(None, [PAGE], {"id": "cardiff", "name": "Cardiff Foodbank", "postcode": "CF24 5BS"}, "2026-10-27", URL)
        self.assertIsNone(new)
def _page(n): return D.text_of(open(os.path.join(ROOT, "tests", "fixtures", n + "_voucher_2026-10-27.html")).read())
class OtherTrussellPages(unittest.TestCase):
    """Same Trussell template elsewhere (saved 27 Oct 2026): each centre gets only its own card."""
    def test_medway_centres_get_own_card_not_office_hours(self):
        P = _page("medway"); office = {"tue": [["09:30", "15:00"]], "wed": [["09:30", "15:00"]], "thu": [["09:30", "15:00"]], "fri": [["09:30", "13:30"]]}
        for item, want in [({"id": "medway/strood-foodbank", "name": "Strood Foodbank", "postcode": "ME2 4TR"}, {"tue": [["11:30", "13:30"]], "fri": [["11:30", "13:30"]]}),
                           ({"id": "medway/midkent-college", "name": "MidKent College", "postcode": "ME7 1FN"}, {"wed": [["09:30", "11:30"]]})]:
            st, new, _ = D.card_check({"status": "TIMES_FOUND", "structured": office}, [P], item, "2026-10-27", URL)
            self.assertEqual((st, new["structured"]), ("changed", want), item["id"])
    def test_thurrock_centre_confirmed_when_unchanged(self):
        P = _page("thurrock"); ot = {"status": "TIMES_FOUND", "structured": {"wed": [["11:00", "13:00"]]}, "raw": "Wednesday 11:00 am to 1:00 pm"}
        st, _, _ = D.card_check(ot, [P], {"id": "thurrock/gateway-peoples-centre", "name": "Gateway People's Centre", "postcode": "SS17 0EY"}, "2026-10-27", URL)
        self.assertEqual(st, "confirmed")
    def test_whole_foodbank_entry_never_borrows_a_centre_by_partial_name(self):
        for n, item in [("harrow", {"id": "harrow", "name": "Harrow Foodbank", "postcode": "HA1 2SP"}),
                        ("thurrock", {"id": "thurrock", "name": "Thurrock Foodbank", "postcode": "SS17 7QH"})]:
            st, new, _ = D.card_check({"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "17:00"]]}}, [_page(n)], item, "2026-10-27", URL)
            self.assertEqual((st, new), ("unconfirmed", None), n)
if __name__ == "__main__": unittest.main()
