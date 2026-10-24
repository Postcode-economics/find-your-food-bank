import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import source_score as ss
R = lambda t, p: {"rates": {"A": {"times": [t, 10], "phone": [p, 10], "fb_page": [0, 10]}}}
class T(unittest.TestCase):
    def test_score(self): self.assertEqual(ss.score(R(80, 100)["rates"]["A"]), 90)
    def test_drop(self): self.assertEqual(len(ss.drops([R(90, 90)] * 3 + [R(50, 90)])[0]), 1)
    def test_small_dip_ok(self): self.assertEqual(ss.drops([R(90, 90)] * 3 + [R(80, 90)])[0], [])
    def test_no_baseline(self): self.assertEqual(ss.drops([R(90, 90), R(0, 0)])[0], [])
