import os, sys, json, tempfile, shutil, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import swep
class Full(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        os.makedirs("scripts"); os.makedirs("overrides"); os.makedirs("logs")
        json.dump({"councils": [{"code": "AAA", "name": "A Council", "nation": "England", "site": "https://a"},
                                {"code": "BBB", "name": "B Council", "nation": "Wales", "site": "https://b"}]}, open("scripts/sweep_sources.json", "w"))
        json.dump([{"code": "AAA", "council": "A Council", "url": "https://a/swep", "homeless_phone": "01234 567890"},
                   {"code": "BBB", "council": "B Council", "url": None, "no_swep_page": True}], open("overrides/swep_sources.json", "w"))
    def tearDown(self): os.chdir(self.cwd); shutil.rmtree(self.d)
    def test_full_and_flags(self):
        page = {"http": 200, "html": "<p>SWEP is now active tonight.</p>"}
        c = swep.full(fetcher=lambda u: page, run_day="2026-10-23")
        self.assertEqual((c["councils"], c["with_swep_page"], c["with_line"]), (2, 1, 1))
        self.assertEqual(c["active"], ["A Council"])
        c2 = swep.full(fetcher=lambda u: {"http": 404}, run_day="2026-10-24")
        log = json.load(open("logs/swep_full.json"))["councils"]
        a = [r for r in log if r["code"] == "AAA"][0]
        self.assertTrue(any("dead page" in f for f in a["flags"]) and any("status active" in f for f in a["flags"]))
        self.assertTrue(os.path.exists("reports/swep_daily.md"))
    def test_watcher_skips_null_urls(self):
        out = swep.run(fetcher=lambda u: {"http": 200, "html": ""}, run_day="2026-10-23")
        self.assertEqual(out["sources"], 1)
if __name__ == "__main__": unittest.main()
