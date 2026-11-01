import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import recheck
PG = {"http": 200, "text": "Goleudy | Paxton Street hostel Swansea. Menu: Community Fridge - now closed. " + "x" * 300, "final_url": "https://goleudy.org/a"}
class IgnorePhrases(unittest.TestCase):
    def test_nav_closed_text_ignored_only_when_listed(self):
        e = {"name": "Paxton Street Hostel (Goleudy)"}
        self.assertTrue(recheck.check(e, dict(e, ignore_phrases=["Community Fridge - now closed"]), PG, "https://goleudy.org/a")["ok"])
        self.assertFalse(recheck.check(e, e, PG, "https://goleudy.org/a")["ok"])
    def test_real_closure_still_caught(self):
        e = {"name": "Paxton Street Hostel (Goleudy)"}
        pg = dict(PG, text=PG["text"] + " Paxton Street has closed.")
        self.assertFalse(recheck.check(e, dict(e, ignore_phrases=["Community Fridge - now closed"]), pg, "https://goleudy.org/a")["ok"])
if __name__ == "__main__": unittest.main()
