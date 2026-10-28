"""Councils with older checked dates move up. No cache and no checked date means no effect."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

def stand(d, state, cache=None):
    os.makedirs(os.path.join(d, "reports"), exist_ok=True)
    os.makedirs(os.path.join(d, "overrides"), exist_ok=True)
    items = [dict(id="a", type="foodbank", website="https://a.org/", postcode="AA1 1AA", tel="01000000000"),
             dict(id="b", type="foodbank", website="https://b.org/", postcode="BB1 1BB", tel="02000000000"),
             dict(id="c", type="foodbank", website="https://c.org/", postcode="CC1 1CC", tel="03000000000")]
    path = os.path.join(d, "data.full.js")
    open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
    json.dump(state, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
    if cache is not None:
        json.dump(cache, open(os.path.join(d, "overrides", "district_cache.json"), "w"))
    return path

class Stale(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json"); LS.MD = os.path.join(self.d, "reports", "learning_review.md")
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_no_cache_no_effect(self):
        stand(self.d, {"sites": {}})
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["stale_note"]); self.assertNotIn("stale_area", str(o["why"]))
    def test_older_area_moves_up(self):
        data = stand(self.d, {"sites": {
            "https://a.org/": {"checked_at": "2026-10-25"},
            "https://b.org/": {"checked_at": "2026-10-25"},
            "https://c.org/": {"checked_at": "2026-10-01"}}},
            {"AA1 1AA": "Recent One", "BB1 1BB": "Recent Two", "CC1 1CC": "Old Council"})
        before = open(data).read()
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("stale_area", o["why"]["https://c.org/"])
        self.assertNotIn("stale_area", o["why"].get("https://a.org/", {}))
        self.assertLessEqual(o["boost"]["https://c.org/"], learning.BOOST_CAP)
        self.assertEqual(open(data).read(), before)

if __name__ == "__main__": unittest.main()
