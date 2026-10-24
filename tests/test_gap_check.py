import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import gap_check as G
class T(unittest.TestCase):
    def test_gaps(self):
        rows = [{"n": "Hope Foodbank", "p": "AB1 2CD"}, {"n": "Town Food Bank", "p": "ZZ9 9ZZ"}, {"n": "Cats Trust", "p": "ZZ9 9ZZ"}, {"n": "Community Pantry", "p": ""}]
        self.assertEqual([r["n"] for r in G.gaps(rows, {"AB12CD"}, "n", "p")], ["Town Food Bank"])
