"""Shelters refresh (28 Oct): the 'every entry has a phone or a labelled council fallback' check ran before the publish
gate, so a new Homeless Link discovery with no number failed the whole run instead of being held for Dean by the gate.
The check must run after the gate (and the fresh-verification guard), on what is actually about to be published."""
import os, unittest
WF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "workflows")

class ContactsCheckAfterGate(unittest.TestCase):
    def order(self, wf, layer):
        s = open(os.path.join(WF, wf), encoding="utf-8").read()
        return [s.index(k) for k in ("python scripts/verify_fresh.py " + layer, "python scripts/publish_gate.py " + layer,
                                     "python scripts/shelter_contacts.py check")]

    def test_shelters(self):
        fresh, gate, contacts = self.order("refresh-shelters.yml", "shelters")
        self.assertLess(fresh, gate); self.assertLess(gate, contacts)

    def test_warmspaces(self):
        fresh, gate, contacts = self.order("refresh-warmspaces.yml", "warmspaces")
        self.assertLess(fresh, gate); self.assertLess(gate, contacts)

if __name__ == "__main__":
    unittest.main()
