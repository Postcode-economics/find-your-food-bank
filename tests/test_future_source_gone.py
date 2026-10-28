"""A source that fails three runs in a row is flagged. Places stay on the map."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class SourceGone(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        sw = open(os.path.join(R, "scripts", "sweep_daily.py"), encoding="utf-8").read()
        self.assertIn("learning.plan(LS, [j[0] for j in jobs], d)", sw)
    def test_three_failures_flag_and_two_do_not(self):
        h = learning.source_history_update({}, {"IFAN": False})
        h = learning.source_history_update(h, {"IFAN": False, "Give Food": True})
        self.assertEqual(learning.sources_gone(h), [])
        h = learning.source_history_update(h, {"IFAN": False})
        self.assertEqual(learning.sources_gone(h), ["IFAN"])
        h = learning.source_history_update(h, {"IFAN": True})
        self.assertEqual(learning.sources_gone(h), [])
    def test_flag_does_not_remove_places(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            os.makedirs(os.path.join(d, "reports"))
            items = [dict(id="a", type="foodbank", name="A", website="https://a.test/", tel="01000000000")]
            path = os.path.join(d, "data.full.js")
            open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            before = open(path).read()
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            learning.record_sources(os.path.join(d, "reports", "source_health.json"), {"IFAN": False})
            learning.record_sources(os.path.join(d, "reports", "source_health.json"), {"IFAN": False})
            learning.record_sources(os.path.join(d, "reports", "source_health.json"), {"IFAN": False})
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertEqual(o["source_gone"], ["IFAN"])
            self.assertIn("not removed", o["source_gone_note"])
            self.assertEqual(open(path).read(), before)
            self.assertEqual(json.loads(open(path).read().split("=", 1)[1].rstrip(";"))["items"][0]["name"], "A")
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)
    def test_missing_file_has_no_effect(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            os.makedirs(os.path.join(d, "reports"))
            open(os.path.join(d, "data.full.js"), "w").write("window.FB_DATA=" + json.dumps({"items": []}) + ";")
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertEqual(o["source_gone"], [])
            self.assertIn("no effect", o["source_gone_note"])
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__":
    unittest.main()
