"""Weather warnings move the named councils up the next run. No warning file, no effect."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, sweep_daily
from test_learning_guards import assert_schedule_and_guards

class Weather(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json"); LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        for sub in ("reports", "overrides", "scripts"): os.makedirs(os.path.join(self.d, sub))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        sw = open(os.path.join(R, "scripts", "sweep_daily.py"), encoding="utf-8").read()
        self.assertIn("learning.plan(LS, [j[0] for j in jobs], d", sw)
        yml = open(os.path.join(R, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read()
        self.assertIn("5 3,11,19 * * *", yml)
    def test_no_file_no_effect(self):
        self._items()
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["weather_note"]); self.assertNotIn("weather", str(o["why"]))
        self.assertEqual(o["council_boost"], {})
    def test_named_council_moves_up(self):
        path = self._items(); before = open(path).read()
        json.dump({"warnings": [{"source": "Met Office", "title": "Yellow warning of wind", "level": "yellow", "areas": ["Leeds"]}]},
                  open(os.path.join(self.d, "reports", "weather.json"), "w"))
        json.dump({"councils": [{"name": "Leeds City Council", "code": "LDS"}, {"name": "Manchester City Council", "code": "MAN"}]},
                  open(os.path.join(self.d, "scripts", "sweep_sources.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("weather", o["why"]["https://leeds.test/"])
        self.assertNotIn("weather", o["why"].get("https://manchester.test/", {}))
        self.assertIn("Leeds City Council", o["council_boost"])
        self.assertNotIn("Manchester City Council", o["council_boost"])
        self.assertLessEqual(o["boost"]["https://leeds.test/"], learning.BOOST_CAP)
        self.assertEqual(open(path).read(), before)
        LS.write(o)
        jobs = [("https://leeds.test/page", "Leeds City Council"), ("https://manchester.test/page", "Manchester City Council")]
        boosts = sweep_daily._weather_boosts(jobs)
        self.assertGreater(boosts["https://leeds.test/page"], 0)
        self.assertNotIn("https://manchester.test/page", boosts)
        s = learning.load(os.devnull)
        for u in boosts: learning.record(s, u, "2026-10-26", True)
        learning.record(s, "https://manchester.test/page", "2026-10-26", True)
        order, _, _ = learning.plan(s, ["https://manchester.test/page", "https://leeds.test/page"], "2026-10-26", boosts=boosts)
        self.assertEqual(order[0], "https://leeds.test/page")
    def _items(self):
        items = [dict(id="a", type="foodbank", website="https://leeds.test/", postcode="LS1 1AA", tel="01000000000"),
                 dict(id="b", type="foodbank", website="https://manchester.test/", postcode="M1 1AA", tel="02000000000")]
        path = os.path.join(self.d, "data.full.js")
        open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
        json.dump({"sites": {}}, open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        json.dump({"LS1 1AA": "Leeds", "M1 1AA": "Manchester"}, open(os.path.join(self.d, "overrides", "district_cache.json"), "w"))
        return path

if __name__ == "__main__": unittest.main()
