import json, os, re, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from hours_fix import clean_phone, apply_phone

class TestCleanPhone(unittest.TestCase):
    def test_two_numbers_or_and(self):
        self.assertEqual(clean_phone("01278445682or01278422568"), ("01278 445682 or 01278 422568", "01278445682"))
        self.assertEqual(clean_phone("01702716607and01702476185")[1], "01702716607")
    def test_encoded_slash_and_shorthand(self):
        self.assertEqual(clean_phone("01483506763%2F01483575128"), ("01483 506763 or 01483 575128", "01483506763"))
        self.assertEqual(clean_phone("01933653346%2F652986"), ("01933 653346 or 01933 652986", "01933653346"))
    def test_html_junk(self):
        self.assertEqual(clean_phone('02088711812"target="_blank"rel="noopenernofollow'), ("020 8871 1812", "02088711812"))
    def test_missing_leading_zero(self):
        self.assertEqual(clean_phone("1984623991"), ("01984 623991", "01984623991"))
    def test_invalid_part_dropped(self):
        self.assertEqual(clean_phone("01872225734or0172669")[0], "01872 225734")
        self.assertEqual(clean_phone("0146057811")[1], "0146057811")  # 01460 has 5-digit local numbers
        self.assertEqual(clean_phone("0141882333"), ("", ""))
    def test_plus44(self):
        self.assertEqual(clean_phone("+44 (0)151 207 3815")[1], "01512073815")
    def test_clean_number_keeps_wording(self):
        x = apply_phone({"phone": "0151 207 3815"}); self.assertEqual((x["phone"], x["tel"]), ("0151 207 3815", "01512073815"))

class TestPublishedData(unittest.TestCase):
    def test_every_tel_is_one_valid_uk_number(self):
        for f in ("data.full.js", "shelters.js", "warmspaces.js"):
            s = open(os.path.join(ROOT, f)).read(); d = json.loads(s[s.index("{"):s.rindex("}") + 1])
            for i in d["items"]:
                if i.get("phone"):
                    self.assertRegex(i.get("tel", ""), r"^0\d{9,10}$", f"{f} {i['id']} {i['phone']!r}")
                    self.assertNotRegex(i["phone"], r"%|<|>|\"|target=", f"{f} {i['id']}")

if __name__ == "__main__": unittest.main()
