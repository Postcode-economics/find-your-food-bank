"""Rule 27 checker formats (Dean, 26 Oct 2026). Fixtures in tests/fixtures/rule27/ are shortened from the source pages
saved during the 26 Oct review (opening_audit/review/pages) and the rule 27 live re-read of 26 Oct 14:24 GMT."""
import os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import discover as D, rule27_formats as R

def fx(name): return open(os.path.join(HERE, "fixtures", "rule27", name), encoding="utf-8").read()
def html(name): return D.text_of(fx(name).replace("\n", "<br>"))   # what the refresh sees: whitespace collapsed

class TrussellNew(unittest.TestCase):
    def test_times_after_postcode_with_day_ranges(self):
        for t in (fx("trussell_new_bangorni.txt"), html("trussell_new_bangorni.txt")):
            self.assertEqual(D.extract_times(t, "BT19 7QT")["structured"], {"mon": [["11:00", "12:30"]], "wed": [["18:30", "20:00"]], "fri": [["13:00", "14:30"]]})
            self.assertEqual(D.extract_times(t, "BT22 1NZ")["structured"], {"thu": [["10:00", "12:00"]]})

    def test_phone_line_hours_are_not_collection_times(self):
        t = fx("trussell_new_bangorni.txt")
        self.assertIn("Monday to Friday 10:00am to 5:00pm", t)
        self.assertNotIn("17:00", str(D.extract_times(t, "BT19 7QT")))
        m = fx("trussell_new_medway.txt")
        for pc, want in (("ME4 5NE", {"mon": [["10:00", "12:30"]], "fri": [["10:00", "12:30"]]}), ("ME7 1FN", {"wed": [["09:30", "11:30"]]})):
            self.assertEqual(D.extract_times(m, pc)["structured"], want)
        b = fx("trussell_new_bradfordnorth.txt")
        self.assertEqual(D.extract_times(b, "BD10 8SA")["structured"], {"mon": [["12:30", "15:00"]]})

    def test_delivery_only_card_is_unclear(self):
        t = fx("trussell_new_chiltern_prestwood.txt")
        self.assertEqual(R.read_centre(t, "HP16 0HJ")["unclear"], "delivery only, no collection times")
        self.assertIsNone(D.extract_times(t, "HP16 0HJ"))

    def test_non_breaking_space_in_postcode(self):
        t = fx("trussell_new_bangorni.txt").replace("BT22 1NZ", "BT22\u00a01NZ")
        self.assertEqual(D.extract_times(t, "BT22 1NZ")["structured"], {"thu": [["10:00", "12:00"]]})
        self.assertEqual(D.extract_times(t.replace("\u00a0", "&nbsp;"), "BT22 1NZ")["structured"], {"thu": [["10:00", "12:00"]]})

    def test_live_check_confirms_only_the_exact_table(self):
        t = fx("trussell_new_medway.txt")
        ok, q = D.live_hours_ok({"thu": [["13:00", "15:00"]], "sat": [["10:00", "12:00"]]}, t, "ME7 5TP")
        self.assertTrue(ok); self.assertIn("Saturday 10:00 am to 12:00 pm", q)
        office = {d: [["09:30", "15:00"]] for d in ("tue", "wed", "thu")}
        self.assertEqual(D.live_hours_ok(office, t, "ME7 5TP"), (False, ""))

class TrussellOld(unittest.TestCase):
    def test_times_before_address(self):
        t = fx("trussell_old_andover.txt")
        self.assertEqual(R.read_centre(t, "SP10 1QP")["layout"], "trussell_old")
        self.assertEqual(D.extract_times(t, "SP10 1QP")["structured"], {d: [["10:00", "16:00"]] for d in ("mon", "tue", "wed", "thu", "fri")})

    def test_neighbouring_centre_not_read(self):
        t = fx("trussell_old_manchester_sc.txt")
        self.assertEqual(D.extract_times(t, "M16 9NW")["structured"], {"wed": [["13:00", "15:00"]]})
        self.assertEqual(D.extract_times(html("trussell_old_manchester_sc.txt"), "M15 5TQ")["structured"], {"fri": [["13:00", "15:00"]]})

    def test_midnight_start_rejected(self):
        t = fx("trussell_old_harlow_midnight.txt")
        self.assertIn("00:00 - 14:00", t)
        self.assertIn("invalid time", R.read_centre(t, "CM17 0PB")["unclear"])
        self.assertIsNone(D.extract_times(t, "CM17 0PB"))

class Columns(unittest.TestCase):
    def test_day_labels_then_values(self):
        t = fx("columns_kingsdarlington.txt")
        r = R.read_centre(t, "DL3 0QT")
        self.assertEqual(r["layout"], "columns")
        self.assertEqual(r["structured"], {"mon": [["10:00", "16:00"]], "thu": [["10:00", "16:00"]]})
        self.assertIn("wed", r["unclear_days"])   # '12:00pm (Taste & See)' has no end time
        self.assertEqual(D.live_hours_ok(r["structured"], t, "DL3 0QT"), (False, ""))   # a listed day is unaccounted for

class Prose(unittest.TestCase):
    def test_between_x_and_y(self):
        self.assertEqual(D.extract_times(fx("prose_dunbar_between.txt"))["structured"], {"wed": [["12:00", "14:00"]]})

    def test_twelve_noon(self):
        t = fx("prose_cefoxford_noon.txt")
        self.assertEqual(D.extract_times(t, "OX3 9LS")["structured"], {"mon": [["12:00", "14:00"]], "wed": [["12:00", "14:00"]]})
        self.assertEqual(D.extract_times(fx("prose_downpatrick_noon.txt"), "BT30 6AW")["structured"], {"fri": [["10:00", "12:00"]]})

    def test_ten_to_twelve_am_means_noon(self):
        self.assertIn("10am - 12pm", R.clean("Fridays 10-12am"))
        self.assertEqual(D.extract_times("Foodbank, Church Hall, AB1 2CD. Open Fridays 10-12am.", "AB1 2CD")["structured"], {"fri": [["10:00", "12:00"]]})

    def test_split_rows_and_bank_holidays(self):
        t = fx("split_rows_swindon.txt")
        self.assertEqual(D.extract_times(t, "SN25 3DF")["structured"], {"tue": [["12:00", "14:00"]], "fri": [["11:00", "13:00"]]})
        self.assertEqual(D.extract_times(t, "SN1 1QS")["structured"], {"mon": [["14:30", "16:30"]], "thu": [["13:30", "16:15"]], "fri": [["14:30", "16:30"]]})
        self.assertEqual(D.extract_times(t, "SN6 7AA")["structured"], {"mon": [["10:00", "12:00"]], "thu": [["10:00", "12:00"]]})

    def test_church_service_and_phone_hours_excluded(self):
        t = "Hope Foodbank, Hall Lane, AB1 2CD. Sunday service 10:30am - 12pm. Collect your parcel Thursday 1pm - 3pm."
        self.assertEqual(D.extract_times(t, "AB1 2CD")["structured"], {"thu": [["13:00", "15:00"]]})
        t = "Hope Foodbank, Hall Lane, AB1 2CD. Our phone line is open Monday 9am - 5pm. Collect your parcel Thursday 1pm - 3pm."
        self.assertEqual(D.extract_times(t, "AB1 2CD")["structured"], {"thu": [["13:00", "15:00"]]})

class Validity(unittest.TestCase):
    def test_reject_end_before_start_and_placeholders(self):
        self.assertIsNone(R.rng("2pm", "1pm"))
        self.assertIsNone(R.rng("12:00 am", "12:00 am"))
        self.assertIsNone(R.rng("3pm", "3pm"))
        self.assertEqual(R.rng("10:30 am", "12:30 pm"), ["10:30", "12:30"])
        card = ("1 results See map X Centre Part of Y Foodbank Z Road AB1 2CD Get directions Collection only Collection times "
                "Monday 12:00 am to 12:00 am Tuesday-Sunday Closed See more information")
        self.assertIsNone(D.extract_times(card, "AB1 2CD"))

class Extra(unittest.TestCase):
    """Cases from the 26 Oct brief: Basingstoke, Northampton, nbsp postcodes, phone wording, bank holidays."""
    def test_basingstoke_neighbour_not_grabbed(self):
        t = fx("trussell_new_basingstoke.txt")
        self.assertIn("The phone is manned Monday to Friday, 9am-4pm", t)
        self.assertEqual(D.extract_times(t, "RG21 8SR")["structured"], {"thu": [["10:30", "12:30"]]})
        self.assertEqual(D.extract_times(t, "RG26 3BF")["structured"], {"tue": [["10:30", "12:30"]]})
        self.assertIsNone(D.extract_times(t, "RG26 4HN"))   # card postcode not on the page: unclear, not the neighbour's table

    def test_northampton_day_headings(self):
        t = fx("day_headings_northampton.txt")
        for pc, want in (("NN1 2LZ", {"tue": [["11:30", "13:30"]]}), ("NN5 6JF", {"sat": [["10:00", "12:00"]]}),
                         ("NN4 8EZ", {"thu": [["12:30", "14:30"]]}), ("NN3 2RA", {"fri": [["09:00", "12:00"]]})):
            self.assertEqual(D.extract_times(t, pc)["structured"], want)
            self.assertTrue(D.live_hours_ok(want, t, pc)[0])
        self.assertFalse(D.live_hours_ok({"thu": [["12:30", "14:30"]]}, t, "NN1 2LZ")[0])   # the neighbour's day

    def test_day_range_is_not_a_heading(self):
        t = ("Storehouse Foodbank, Unit 1, Feltham TW13 7LX. MONDAY - THURSDAY 9:30AM - 4:30PM. FRIDAY Closed. "
             "SATURDAY Closed. SUNDAY Closed.")
        self.assertIsNone(R.day_headings(R.clean(t), "TW13 7LX"))

    def test_bs16_nbsp(self):
        t = "Mangotsfield Foodbank, Resound Church, Bristol BS16\xa09BP. Open Fridays 10am - 12pm."
        self.assertEqual(D.extract_times(t, "BS16 9BP")["structured"], {"fri": [["10:00", "12:00"]]})

    def test_phone_wordings_dropped(self):
        for w in ("Our phone lines are monitored Monday - Friday 09:30-13:30.", "Phoneline open Tuesday to Friday, 10am to 12:30pm.",
                  "Please note that the office and telephones are manned as follows: Tuesdays 9.30am - 3.00pm."):
            t = "Hope Foodbank, Hall Lane, AB1 2CD. %s Collect your parcel Thursday 1pm - 3pm." % w
            self.assertEqual(D.extract_times(t, "AB1 2CD")["structured"], {"thu": [["13:00", "15:00"]]}, w)

    def test_except_bank_holidays_day_list(self):
        t = "Hope Foodbank, Hall Lane, AB1 2CD. Open Monday (except bank holidays) & Thursday 10am - 12pm."
        self.assertEqual(D.extract_times(t, "AB1 2CD")["structured"], {"mon": [["10:00", "12:00"]], "thu": [["10:00", "12:00"]]})

if __name__ == "__main__":
    unittest.main()
