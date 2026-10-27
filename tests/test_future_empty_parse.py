"""A page that answers but parses to nothing is flagged and moved up. It is not removed."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, learning_signals as LS, directories
from test_learning_guards import assert_schedule_and_guards

class EmptyParse(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.empty_parse", fc)
        self.assertIn("5 3,11,19 * * *", open(os.path.join(R, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read())
    def test_only_a_drop_to_nothing_counts(self):
        self.assertFalse(learning.empty_parse(200, 0, None))
        self.assertFalse(learning.empty_parse(404, 0, 5))
        self.assertFalse(learning.empty_parse(200, 3, 5))
        self.assertFalse(learning.empty_parse(200, 0, 0))
        self.assertTrue(learning.empty_parse(200, 0, 4))
        self.assertTrue(learning.empty_parse(200, 12, 500, minimum=200))
        self.assertFalse(learning.empty_parse(200, 12, None, minimum=200))
    def test_flag_moves_the_site_up_and_leaves_the_map(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            os.makedirs(os.path.join(d, "reports"))
            items = [dict(id="a", type="foodbank", website="https://leeds.test/", tel="01000000000")]
            path = os.path.join(d, "data.full.js")
            open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            before = open(path).read()
            json.dump({"sites": {"https://leeds.test/": {"empty_parse": True, "http": 200, "fail_runs": 0}}},
                      open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertIn("empty_parse", o["why"]["https://leeds.test/"])
            self.assertLessEqual(o["boost"]["https://leeds.test/"], learning.BOOST_CAP)
            self.assertIn("parser found nothing", o["empty_note"])
            self.assertEqual(open(path).read(), before)
            self.assertIn("parser found nothing", "\n".join(LS.digest_lines(o)))
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)
    def test_no_flag_without_the_mark(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            os.makedirs(os.path.join(d, "reports"))
            open(os.path.join(d, "data.full.js"), "w").write("window.FB_DATA=" + json.dumps({"items": [dict(id="a", type="foodbank", website="https://a.test/", tel="01000000000")]}) + ";")
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertIn("no effect", o["empty_note"])
            self.assertNotIn("empty_parse", str(o["why"]))
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)
    def test_directory_flags_a_short_parse_and_returns_nothing(self):
        def fetch(url): return {"http": 200, "html": "<html>maintenance</html>", "sha256": "x"}
        c, st = directories.ifan(fetch, previous=800)
        self.assertEqual(c, [])
        self.assertTrue(st["empty_parse"])
        self.assertIn("schema", st["status"])
        c2, st2 = directories.ifan(fetch)
        self.assertEqual(c2, [])
        self.assertNotIn("empty_parse", st2)

if __name__ == "__main__":
    unittest.main()
