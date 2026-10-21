import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import hours_norm as H
class T(unittest.TestCase):
    def test_osm_days(self):
        self.assertEqual(H.normalise_hours("Mo-We,Fr 20:00-21:30"), {d: "20:00 - 21:30" for d in ("Mon", "Tue", "Wed", "Fri")})
        self.assertEqual(list(H.normalise_hours("Mo-We,Fr 20:00-21:30")), ["Mon", "Tue", "Wed", "Fri"])
    def test_osm_overnight(self):
        self.assertEqual(H.normalise_hours("Mo-Su 17:00-10:00"), {d: "17:00 - 10:00" for d in H.DAYS})
    def test_247(self):
        self.assertEqual(H.normalise_hours("24/7"), {d: "24 hours" for d in H.DAYS})
    def test_osm_rules_and_off(self):
        self.assertEqual(H.normalise_hours("Mo-Fr 09:00-12:00,13:00-17:00; We off; Su 10:00-24:00"),
                         {"Mon": "09:00 - 12:00 / 13:00 - 17:00", "Tue": "09:00 - 12:00 / 13:00 - 17:00", "Thu": "09:00 - 12:00 / 13:00 - 17:00",
                          "Fri": "09:00 - 12:00 / 13:00 - 17:00", "Sun": "10:00 - 23:59"})
    def test_text_kept_once(self):
        s = "8pm-8am, only when severe weather provision is open"
        self.assertEqual(H.normalise_hours(s), s)
        self.assertEqual(H.normalise_hours("Fortnightly | Fortnightly"), "Fortnightly")
        self.assertEqual(H.normalise_hours("  Mo-Fr  sometimes  "), "Mo-Fr sometimes")
    def test_dict_order(self):  # the two warm spaces found out of order (Cat and Mouse Library, Central Library)
        h = H.normalise_hours({"Tue": "a", "Thu": "b", "Wed": "c", "Sat": "d"}); self.assertEqual(list(h), ["Tue", "Wed", "Thu", "Sat"])
        h = H.normalise_hours({"Mon": "1", "Wed": "1", "Thu": "1", "Tue": "1", "Fri": "1", "Sat": "1", "Sun": "1"}); self.assertEqual(list(h), H.DAYS)
        self.assertEqual(list(H.normalise_hours({"Wednesday": "x", "monday": "y"})), ["Mon", "Wed"])
    def test_fb_structured_order(self):
        ot = {"status": "TIMES_FOUND", "structured": {"fri": [["09:00", "14:00"]], "mon": [["13:00", "14:00"], ["09:00", "10:00"]], "wed": [["09:00", "14:00"]]}}
        n = H.normalise_fb(ot); self.assertEqual(list(n["structured"]), ["mon", "wed", "fri"]); self.assertEqual(n["structured"]["mon"][0], ["09:00", "10:00"])
    def test_fb_lines_once(self):
        n = H.normalise_fb({"status": "TIMES_TEXT_ONLY", "lines": ["Tue 10am", "Tue  10am", "Thu 1pm"]}); self.assertEqual(n["lines"], ["Tue 10am", "Thu 1pm"])
    def test_apply_counts(self):
        xs = [{"hours": "24/7"}, {"hours": {"Mon": "09:00 - 10:00"}}]; self.assertEqual(H.apply(xs, "hours"), 1)
if __name__ == "__main__": unittest.main()
