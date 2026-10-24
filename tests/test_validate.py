import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate as V
class T(unittest.TestCase):
    def test_checks(self):
        self.assertEqual(V.problems(dict(name="Tadley", phone="01256 123456", postcode="RG26 3AB")), [])
        self.assertEqual(V.problems(dict(name="", phone="12345", postcode="BAD")), ["a phone", "c postcode", "d name"])
        self.assertEqual(V.problems(dict(name="X", opening_times={"structured": {"mon": [["14:00", "12:00"]]}})), ["b times"])
        self.assertTrue(V.phone_ok("+44 20 7946 0000")); self.assertTrue(V.phone_ok("116 123")); self.assertTrue(V.phone_ok("01278 445682 or 01278 422568")); self.assertFalse(V.phone_ok("01278 445682 or 123"))
