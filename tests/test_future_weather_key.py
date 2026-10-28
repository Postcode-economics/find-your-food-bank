"""A failed weather key is named. It does not add areas. A real warning already on file still can."""
import os, sys, json, datetime, tempfile, shutil, unittest, urllib.error
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, weather
from test_learning_guards import assert_schedule_and_guards

class Key(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "reports", "learning_signals.json")
        LS.MD = os.path.join(self.d, "reports", "learning_review.md")
        for sub in ("reports", "overrides", "scripts"): os.makedirs(os.path.join(self.d, sub))
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def _items(self):
        items = [dict(id="a", type="foodbank", website="https://leeds.test/", postcode="LS1 1AA", tel="01000000000"),
                 dict(id="b", type="foodbank", website="https://manchester.test/", postcode="M1 1AA", tel="02000000000")]
        path = os.path.join(self.d, "data.full.js")
        open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
        json.dump({"sites": {}}, open(os.path.join(self.d, "reports", "full_check_state.json"), "w"))
        json.dump({"LS1 1AA": "Leeds", "M1 1AA": "Manchester"}, open(os.path.join(self.d, "overrides", "district_cache.json"), "w"))
        json.dump({"councils": [{"name": "Leeds City Council", "code": "LDS"}, {"name": "Manchester City Council", "code": "MAN"}]},
                  open(os.path.join(self.d, "scripts", "sweep_sources.json"), "w"))
        return path
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        yml = open(os.path.join(R, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read()
        self.assertIn("5 3,11,19 * * *", yml)
    def test_http_status_is_recorded_without_a_body(self):
        line = weather.error_line("Met Office", urllib.error.HTTPError("https://example.test", 401, "no", None, None))
        self.assertEqual(line, "Met Office: HTTP 401")
        self.assertNotIn("html", line)
    def test_a_key_failure_adds_no_areas(self):
        path = self._items(); before = open(path).read()
        json.dump({"warnings": [], "errors": ["Natural Resources Wales: no API key", "Met Office: HTTP 403"]},
                  open(os.path.join(self.d, "reports", "weather.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no API key", o["weather_key_note"])
        self.assertIn("403", o["weather_key_note"])
        self.assertIn("No areas were added", o["weather_key_note"])
        self.assertIn("no effect", o["weather_note"])
        self.assertNotIn("weather", str(o["why"]))
        self.assertEqual(o["council_boost"], {})
        self.assertEqual(open(path).read(), before)
    def test_a_real_warning_still_moves_its_own_area(self):
        self._items()
        json.dump({"warnings": [{"source": "Met Office", "title": "Yellow warning of wind", "level": "yellow", "areas": ["Leeds"]}],
                   "errors": ["Natural Resources Wales: no API key"]},
                  open(os.path.join(self.d, "reports", "weather.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("weather", o["why"]["https://leeds.test/"])
        self.assertNotIn("weather", o["why"].get("https://manchester.test/", {}))
        self.assertIn("Leeds City Council", o["council_boost"])
        self.assertNotIn("Manchester City Council", o["council_boost"])
        self.assertNotIn("Manchester", o["weather_key_note"])

if __name__ == "__main__":
    unittest.main()
