"""Demand prediction uses only documented feeds. Missing or unsourced calendars do nothing."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

def stand(d):
    for sub in ("reports", "overrides"): os.makedirs(os.path.join(d, sub), exist_ok=True)
    items = [dict(id="a", type="foodbank", website="https://a.org/", postcode="LS1 1AA", tel="01000000000"),
             dict(id="b", type="foodbank", website="https://b.org/", postcode="M1 1AA", tel="02000000000")]
    path = os.path.join(d, "data.full.js")
    open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
    json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
    json.dump({"LS1 1AA": "Leeds", "M1 1AA": "Manchester"}, open(os.path.join(d, "overrides", "district_cache.json"), "w"))
    return path

class Forecast(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; learning.STATE = os.path.join(self.d, "reports", "learning_state.json")
        LS.OUT = os.path.join(self.d, "o"); LS.MD = os.path.join(self.d, "m")
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
    def test_nothing_documented_means_no_effect(self):
        stand(self.d)
        json.dump({"school_holidays": "not included - no single official UK source"}, open(os.path.join(self.d, "reports", "holidays.json"), "w"))
        json.dump({"dates": ["2026-10-26"]}, open(os.path.join(self.d, "reports", "benefit_dates.json"), "w"))  # no source URL
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no effect", o["forecast_note"])
        self.assertNotIn("forecast", str(o["why"]))
        self.assertIn("no documented calendar", o["forecast_note"])
        self.assertIn("not included", o["forecast_note"])
    def test_cold_warning_and_sourced_benefit_date(self):
        data = stand(self.d); before = open(data).read()
        json.dump({"warnings": [
            {"title": "Yellow warning of wind", "level": "yellow", "areas": ["Leeds"]},
            {"title": "Amber warning of snow and ice", "level": "amber", "areas": ["Leeds"]}]},
            open(os.path.join(self.d, "reports", "weather.json"), "w"))
        json.dump({"source": "https://www.gov.uk/guidance/benefit-payment-dates", "dates": ["2026-10-27"]},
                  open(os.path.join(self.d, "reports", "benefit_dates.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("forecast", o["why"]["https://a.org/"])
        self.assertIn("forecast", o["why"]["https://b.org/"])  # benefit date is national; snow is Leeds only, so Leeds is higher
        self.assertGreater(o["why"]["https://a.org/"]["forecast"], o["why"]["https://b.org/"]["forecast"])
        self.assertLessEqual(o["boost"]["https://a.org/"], learning.BOOST_CAP)
        self.assertIn("https://www.gov.uk/guidance/benefit-payment-dates", o["forecast_note"])
        self.assertEqual(open(data).read(), before)
    def test_school_holidays_need_a_source_url(self):
        stand(self.d)
        json.dump({"school_holidays": [{"start": "2026-10-20", "end": "2026-10-30", "council": "Leeds"}]},
                  open(os.path.join(self.d, "reports", "holidays.json"), "w"))
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn("no documented school-holiday calendar", o["forecast_note"])
        self.assertNotIn("forecast", str(o["why"]))

if __name__ == "__main__": unittest.main()
