import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import layer_review as L
class T(unittest.TestCase):
    def test_diff(self):
        o = {"items": [{"id": "a", "name": "A", "tier": "verified"}, {"id": "b", "name": "B"}]}
        n = {"items": [{"id": "a", "name": "A", "tier": "unverified"}, {"id": "c", "name": "C", "upcoming": True, "scheme_dates": "Opens 7 Dec 2026"}],
             "recently_closed": [{"id": "b", "name": "B", "closed_reason": "Season ended"}]}
        d = L.diff(o, n)
        self.assertEqual([x["id"] for x in d["added"]], ["c"]); self.assertEqual(d["removed"][0]["reason"], "Season ended")
        self.assertEqual(len(d["tier_flips"]), 1); self.assertEqual(d["upcoming"], ["C – Opens 7 Dec 2026"])
if __name__ == "__main__": unittest.main()
