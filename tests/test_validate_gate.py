import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate as v
D = lambda n: 'x={"items": [%s]}' % ",".join(["{}"] * n)
class T(unittest.TestCase):
    def test_ok(self): self.assertEqual(v.gate({"foodbanks": D(95)}, {"foodbanks": D(100)}), {})
    def test_drop(self): self.assertIn("foodbanks", v.gate({"foodbanks": D(89)}, {"foodbanks": D(100)}))
    def test_parse(self): self.assertIn("shelters", v.gate({"shelters": "x={broken"}, {"shelters": D(5)}))
    def test_no_last(self): self.assertEqual(v.gate({"foodbanks": D(3)}, {}), {})
