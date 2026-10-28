"""Count food-bank postcodes missing from the council cache. Do not look any up or guess one."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class Gaps(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        for sub in ("reports", "overrides"): os.makedirs(os.path.join(self.d, sub))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def _items(self):
        items = [dict(id="a", type="foodbank", website="https://a.test/", postcode="LS1 1AA", tel="01000000000"),
                 dict(id="b", type="foodbank", website="https://b.test/", postcode="M1 1AA", tel="02000000000"),
                 dict(id="c", type="foodbank", website="https://a.test/", postcode="LS1 1AA", tel="01000000000")]
        path = os.path.join(self.d, "data.full.js")
        open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
        json.dump({"sites": {"https://a.test/": {"checked_at": "2026-10-01"}, "https://b.test/": {"checked_at": "2026-10-20"}}},
                  open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        return path
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        src = open(os.path.join(R, "scripts", "learning_signals.py"), encoding="utf-8").read()
        self.assertNotIn("postcodes.io", src[src.index("def cache_gaps"):src.index("def districts_for")])
    def test_missing_file_has_no_effect(self):
        os.remove(os.path.join(self.d, "overrides", "district_cache.json")) if os.path.exists(os.path.join(self.d, "overrides", "district_cache.json")) else None
        self._items()
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["cache_gap_note"])
        self.assertNotIn("stale_area", str(o["why"]))
    def test_a_missing_row_is_counted_and_not_guessed(self):
        path = self._items(); before = open(path).read()
        cache = {"LS1 1AA": "Leeds"}
        json.dump(cache, open(os.path.join(self.d, "overrides", "district_cache.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("1 food-bank postcode has no council row", o["cache_gap_note"])
        self.assertIn("no council was guessed", o["cache_gap_note"])
        self.assertNotIn("Manchester", o["cache_gap_note"])
        self.assertEqual(json.load(open(os.path.join(self.d, "overrides", "district_cache.json"))), cache)
        self.assertNotIn("https://b.test/", LS.districts_for([dict(website="https://b.test/", postcode="M1 1AA")]))
        self.assertEqual(open(path).read(), before)
        self.assertNotIn("stale_area", o["why"].get("https://b.test/", {}))

if __name__ == "__main__":
    unittest.main()
