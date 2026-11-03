"""Rule 82 in the sweep (Dean 3 Nov 2026): repair a hand-checked card, and a live-data fault in a layer file the sweep
does not change or publish does not stop the sweep's own outputs. Anything the run caused still blocks."""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import restore_verified_fields
import sweep_gate as G

LINE = "Bristol connection needed: ask Bristol Council's homelessness team to refer you."
VER = {"hl-st-mungos-longhills": {"verified_on": "2026-10-31", "referral": LINE, "phone": "0117 352 6800", "name": "St Mungo's - Longhills"}}

class RepairDontDrop(unittest.TestCase):
    def test_broken_hand_checked_card_gets_verified_data_back(self):
        items = [{"id": "hl-st-mungos-longhills", "card_type": "referral_hostel", "name": "St Mungo's - Longhills", "phone": "", "referral_route": None}]
        self.assertEqual(restore_verified_fields(items, VER), ["hl-st-mungos-longhills"])
        self.assertEqual(items[0]["referral"], LINE)
        self.assertEqual(items[0]["referral_route"], LINE)
        self.assertEqual(items[0]["phone"], "0117 352 6800")
    def test_never_overwrites_or_invents(self):
        items = [{"id": "hl-st-mungos-longhills", "name": "St Mungo's - Longhills", "phone": "0117 000 0000", "referral": LINE},
                 {"id": "not-hand-checked", "phone": ""}]
        self.assertEqual(restore_verified_fields(items, VER), [])
        self.assertEqual(items[0]["phone"], "0117 000 0000")
        self.assertEqual(items[1]["phone"], "")

class ScopeOfABlock(unittest.TestCase):
    T = "tests/test_shelter_sources.py::HandCheck::test_published_cards_match_the_hand_check"
    NAMED = [("Shelters", "hl-st-mungos-longhills", "St Mungo's - Longhills")]
    def test_live_fault_in_unpublished_unchanged_layer_publishes_and_names_place(self):
        ok, places = G.decide([self.T], [self.T], set(), {"stamp.js"}, self.NAMED)
        self.assertTrue(ok); self.assertEqual(places, self.NAMED)
    def test_failure_this_run_caused_blocks(self):
        self.assertFalse(G.decide([self.T, "tests/test_sweep.py::X::y"], [self.T], set(), set(), self.NAMED)[0])
    def test_changed_layer_blocks(self):
        self.assertFalse(G.decide([self.T], [self.T], {"Shelters"}, set(), self.NAMED)[0])
    def test_published_layer_blocks(self):
        self.assertFalse(G.decide([self.T], [self.T], set(), {"shelters.js"}, self.NAMED)[0])
    def test_unnamed_failure_blocks(self):
        self.assertFalse(G.decide(["tests/test_layers.py::Count::test_min"], ["tests/test_layers.py::Count::test_min"], set(), set(), [])[0])
    def test_parsing(self):
        out = 'FAILED %s - AssertionError: None != "Bristol connection needed: ask Bristol C[91 chars]you."\n' % self.T
        self.assertEqual(G.failed_ids(out), [self.T])
        items = [{"id": "hl-st-mungos-longhills", "name": "St Mungo's - Longhills", "referral": LINE}, {"id": "hl-other-place", "name": "Other"}]
        self.assertEqual([p[1] for p in G.places_named(out, [("Shelters", items)])], ["hl-st-mungos-longhills"])
    def test_sweep_does_not_publish_layer_files(self):
        wf = open(os.path.join(ROOT, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read()
        pub = G.published_by_sweep(wf)
        self.assertTrue(pub)
        self.assertNotIn("shelters.js", pub); self.assertNotIn("warmspaces.js", pub)
        self.assertIn("scripts/sweep_gate.py", wf)

if __name__ == "__main__":
    unittest.main()
