import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gap_check
class T(unittest.TestCase):
    def test_tsv_registered_only(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "x.txt")
        open(p, "w").write("charity_name\tcharity_registration_status\tcharity_contact_postcode\nA FOODBANK\tRegistered\tZZ9 9ZZ\nB FOODBANK\tRemoved\tZZ9 9ZY\nC CHURCH\tRegistered\tZZ9 9ZX\n")
        md = gap_check.MD; gap_check.MD = os.path.join(d, "o.md")
        try: g = gap_check.main(p)
        finally: gap_check.MD = md
        self.assertEqual([r["charity_name"] for r in g], ["A FOODBANK"])
