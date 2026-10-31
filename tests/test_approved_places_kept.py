"""Approvals Dean has given must never be dropped by a later merge (Sidley was lost in #328)."""
import json, os, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")

class ApprovedPlacesKept(unittest.TestCase):
    def test_known_approvals_present(self):
        d = json.load(open(os.path.join(ROOT, "overrides", "approved_new_places.json"), encoding="utf-8"))
        for layer, pid in [("foodbanks", "bexhill/sidley"), ("foodbanks", "st-peter-st-pauls-pantry"),
                           ("foodbanks", "littlehampton-community-fridge"),
                           ("warmspaces", "sheff-shipshape-community-hub"),
                           ("shelters", "man-hastings-wuth-night-shelter"), ("shelters", "man-mary-rose-court-basingstoke"),
                           ("shelters", "man-ymca-basingstoke"), ("shelters", "man-ymca-watford-charter")]:
            self.assertIn(pid, d.get(layer, {}), f"{layer}/{pid} approval was dropped")

if __name__ == "__main__":
    unittest.main()
