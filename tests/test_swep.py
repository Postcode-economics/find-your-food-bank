import sys, os, unittest, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import swep as W
class T(unittest.TestCase):
    def test_active(self): self.assertEqual(W.classify("Birmingham's Severe Weather Emergency Protocol has been activated due to snow.")[0], "active")
    def test_deactivated(self): self.assertEqual(W.classify("SWEP has been deactivated in Bristol, but support is still available.")[0], "not active")
    def test_generic(self): self.assertEqual(W.classify("SWEP provides emergency accommodation during severe weather.")[0], "unknown")
    def test_conditional_not_active(self): self.assertEqual(W.classify("SWEP is activated when there is a severe weather warning.")[0], "unknown")
    def test_old_news(self): self.assertTrue(W.classify("Published: Thursday, 8th January 2026. The Severe Weather Emergency Protocol has been activated due to snow.", "2026-10-23")[0].startswith("old notice"))
    def test_when_prefix(self): self.assertEqual(W.classify("When SWEP is activated SWEP is activated when: the Met Office issues a red warning")[0], "unknown")
    def test_none(self): self.assertEqual(W.classify("Bin collection days")[0], "no SWEP wording")
    def test_run_changes(self):
        d = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(d); os.makedirs("overrides"); os.makedirs("logs")
        try:
            json.dump([{"council": "X", "url": "https://x.gov.uk/swep"}], open(W.SRC, "w"))
            f = lambda u: {"http": 200, "html": "<p>SWEP is now active tonight.</p>"}
            r = W.run(fetcher=f, run_day="2026-11-20"); self.assertEqual(r["active"], ["X"]); self.assertEqual(len(r["changes"]), 1)
            f2 = lambda u: {"http": 200, "html": "<p>SWEP has been stood down.</p>"}
            r = W.run(fetcher=f2, run_day="2026-11-21"); self.assertEqual(r["changes"][0]["to"], "not active")
        finally: os.chdir(cwd)
if __name__ == "__main__": unittest.main()
