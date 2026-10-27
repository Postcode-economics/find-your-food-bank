"""Cardiff Foodbank (27 Oct 2026): every centre showed Mon-Fri 09:30-13:30, the 'Our phone lines are monitored' line printed
on every Trussell centre card. Times must come from each centre's own card, matched by postcode or name. Saved page:
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
            st, new, why = D.card_check({"status": "TIMES_FOUND", "structured": PHONE}, [PAGE], {"name": name, "postcode": pc}, "2026-10-27", URL)
            self.assertEqual(st, "changed", k); self.assertEqual(new["structured"], WANT[k], k)
            st2, _, _ = D.card_check(new, [PAGE], {"name": name, "postcode": pc}, "2026-10-27", URL)
            self.assertEqual(st2, "confirmed", k)
    def test_phone_hours_never_confirmed_from_page(self):
        st, _, _ = D.confirm_times({"status": "TIMES_FOUND", "structured": PHONE}, [PAGE])
        self.assertNotEqual(st, "confirmed")
        self.assertIsNone(D.extract_times("Our phone lines are monitored Monday - Friday 09:30-13:30", None))
    def test_warehouse_has_no_card(self):
        st, new, _ = D.card_check(None, [PAGE], {"name": "Cardiff Foodbank", "postcode": "CF24 5BS"}, "2026-10-27", URL)
        self.assertIsNone(new)
if __name__ == "__main__": unittest.main()
