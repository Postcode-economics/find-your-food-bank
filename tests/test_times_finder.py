import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import trussell_times as T
CARD = ("I have a food voucher 2 results See map Close Brightlingsea Foodbank Part of Colchester Foodbank 01206 621998 "
        "Brightlingsea Parish Hall Victoria Place Brightlingsea, Essex CO7 0BP Get directions Collection and delivery Collection times "
        "Closed today Monday-Tuesday Closed Wednesday 10:30 am to 12:30 pm Thursday-Sunday Closed Delivery times Closed today Monday-Sunday Closed "
        "Frogmore Distribution Centre (Fortnightly) Part of St Albans & District Foodbank 01727 613019 Holy Trinity Church 37 Frogmore St Albans AL2 2JU "
        "Get directions Collection only Collection times Open today until 1:00 pm Monday-Tuesday Closed Wednesday 11:30 am to 1:00 pm Thursday-Sunday Closed "
        "Broxburn (by appointment only) Part of West Lothian Foodbank Broxburn EH52 5EL Get directions Collection times Closed today Tuesday 12:00 am to 12:00 am Thursday 12:00 am to 12:00 am "
        "See more information")
class TTest(unittest.TestCase):
    def setUp(self): self.c = T.parse_cards(CARD)
    def test_cards(self): self.assertEqual([c["postcode"] for c in self.c], ["CO7 0BP", "AL2 2JU", "EH52 5EL"])
    def test_weekly(self):
        ot = T.to_ot(self.c[0], "u", "2026-10-23"); self.assertEqual(ot["status"], "TIMES_FOUND"); self.assertEqual(ot["structured"], {"wed": [["10:30", "12:30"]]})
    def test_fortnightly_as_written(self):
        ot = T.to_ot(self.c[1], "u", "2026-10-23"); self.assertEqual(ot["status"], "TIMES_TEXT_ONLY"); self.assertIn("Fortnightly", ot["raw"])
    def test_today_banner_ignored(self): self.assertNotIn("1:00 pm Monday", self.c[1]["raw"])
    def test_placeholder_times_not_used(self):
        ot = T.to_ot(self.c[2], "u", "2026-10-23"); self.assertEqual(ot["status"], "TIMES_TEXT_ONLY"); self.assertIn("appointment", ot["raw"])
    def test_match_postcode(self):
        c, how = T.match({"name": "Brightlingsea", "postcode": "co70bp"}, self.c); self.assertEqual(c["name"], "Brightlingsea Foodbank"); self.assertEqual(how, "postcode")
    def test_no_match_no_guess(self):
        c, how = T.match({"name": "Somewhere", "postcode": "ZZ1 1ZZ"}, self.c); self.assertIsNone(c)
    def test_day_range(self):
        cs = T.parse_cards("X Hub Part of York Foodbank Road AB1 2CD Get directions Collection times Tuesday-Wednesday 11:00 am to 1:00 pm Delivery times")
        self.assertEqual(T.to_ot(cs[0], "u", "d")["structured"], {"tue": [["11:00", "13:00"]], "wed": [["11:00", "13:00"]]})
import times_finder as F
import discover as D
class Old(unittest.TestCase):
    def test_old_template(self):
        t = F.fix_text("Horfield Food Bank Outlet Address Ebenezer Church, 286 Filton Avenue, Bristol, BS7 0BA Get directions Opening day Thursday Opening hours 1:30pm - 3:00pm Public Transport")
        ot = D.extract_times(t, "BS7 0BA"); self.assertEqual(ot["status"], "TIMES_FOUND"); self.assertEqual(ot["structured"], {"thu": [["13:30", "15:00"]]})
if __name__ == "__main__": unittest.main()
