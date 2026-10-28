"""Each parser still reads the small example page saved for it. The example is not a full personal page."""
import os, sys, json, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import directories
from test_learning_guards import assert_schedule_and_guards
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "parsers")

class Fixtures(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_examples_stay_small(self):
        for name in ("ifan.txt", "homeless.snippet", "open_innovations.json"):
            raw = open(os.path.join(FIX, name), encoding="utf-8").read()
            self.assertLess(len(raw), 800, name)
            self.assertNotIn("<!DOCTYPE", raw)
            self.assertNotIn("<html", raw.lower())
    def test_ifan_example(self):
        c = directories.parse_ifan(open(os.path.join(FIX, "ifan.txt"), encoding="utf-8").read())
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["postcode"], "TQ6 9LJ")
        self.assertEqual(c[0]["website"], "https://example.test/")
        self.assertEqual(c[0]["name"], "Example Pantry")
    def test_homeless_example(self):
        c = directories.parse_hl_service("example-hostel", open(os.path.join(FIX, "homeless.snippet"), encoding="utf-8").read())
        self.assertEqual(c["postcode"], "AB1 2CD")
        self.assertEqual(c["website"], "https://example.test/")
        self.assertEqual(c["phone"], "01000000000")
    def test_open_innovations_example(self):
        places = json.load(open(os.path.join(FIX, "open_innovations.json"), encoding="utf-8"))
        c = directories.parse_oi(places, {"bham": {"title": "Birmingham", "url": "https://example.test/b"}})
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["postcode"], "B18 7AF")
        self.assertEqual(c[0]["website"], "https://example.test/")

if __name__ == "__main__":
    unittest.main()
