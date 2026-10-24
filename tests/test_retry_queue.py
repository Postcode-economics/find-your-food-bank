import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import full_check as F
class T(unittest.TestCase):
    def test_order(self): self.assertEqual(F.retry_first(["a", "b", "c", "d"], ["c", "x"]), ["c", "a", "b", "d"])
    def test_empty(self): self.assertEqual(F.retry_first(["b", "a"], []), ["b", "a"])
