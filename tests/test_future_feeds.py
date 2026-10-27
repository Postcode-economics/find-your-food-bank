"""A new link on a known official host is flagged. No place is added."""
import os, sys, json, datetime, tempfile, shutil, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import official_feeds, learning, learning_signals as LS
from test_learning_guards import assert_schedule_and_guards

class OfficialFeeds(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        sw = open(os.path.join(R, "scripts", "sweep_daily.py"), encoding="utf-8").read()
        self.assertIn("learning.plan(LS, [j[0] for j in jobs], d)", sw)
        self.assertIn("official_feeds.scan", sw)
        cfg = json.load(open(os.path.join(R, "overrides", "official_feeds.json"), encoding="utf-8"))
        self.assertEqual(cfg["hosts"], ["foodaidnetwork.org.uk", "givefood.org.uk", "open-innovations.github.io"])
    def test_only_new_links_on_listed_hosts(self):
        known = ["https://www.givefood.org.uk/api/2/"]
        hosts = ["givefood.org.uk"]
        text = "see https://www.givefood.org.uk/api/2/ and https://www.givefood.org.uk/needs/new-list and https://example.com/list"
        got = official_feeds.new_in(text, known, hosts)
        self.assertEqual(got, ["https://www.givefood.org.uk/needs/new-list"])
        self.assertEqual(official_feeds.scan("https://www.givefood.org.uk/x", path=os.path.join(tempfile.mkdtemp(), "missing.json")), [])
    def test_the_note_adds_nothing(self):
        d = tempfile.mkdtemp(); old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        try:
            LS.ROOT = d; learning.STATE = os.path.join(d, "reports", "learning_state.json")
            LS.OUT = os.path.join(d, "reports", "learning_signals.json"); LS.MD = os.path.join(d, "reports", "learning_review.md")
            for sub in ("reports", "overrides"): os.makedirs(os.path.join(d, sub))
            items = [dict(id="a", type="foodbank", name="A", website="https://a.test/")]
            path = os.path.join(d, "data.full.js")
            open(path, "w").write("window.FB_DATA=" + json.dumps({"items": items}) + ";")
            before = open(path).read()
            json.dump({"sites": {}}, open(os.path.join(d, "reports", "full_check_state.json"), "w"))
            json.dump({"known": ["https://www.givefood.org.uk/api/2/"], "hosts": ["givefood.org.uk"]}, open(os.path.join(d, "overrides", "official_feeds.json"), "w"))
            json.dump({"urls": ["https://www.givefood.org.uk/needs/new-list"], "added": False}, open(os.path.join(d, "reports", "new_official_feeds.json"), "w"))
            o = LS.build(datetime.date(2026, 10, 26))
            self.assertIn("nothing added", o["feed_note"])
            self.assertIn("new-list", o["feed_note"])
            self.assertEqual(open(path).read(), before)
        finally:
            LS.ROOT, LS.OUT, LS.MD, learning.STATE = old; shutil.rmtree(d)

if __name__ == "__main__":
    unittest.main()
