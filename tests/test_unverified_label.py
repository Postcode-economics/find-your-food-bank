"""'Unverified – call before you go' only when hours are not confirmed (Dean, 25 Oct 2026).
Confirmed/updated times (or real hours from a named page) checked in the last 7 days show
'Times checked {date} – call before you go'. Computed from data fields at load; the window rolls."""
import os, sys, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.join(os.path.dirname(__file__), "..")
LJ = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
DAY = 864e5

class Static(unittest.TestCase):
    def test_strings(self):
        self.assertIn("tchk:'Times checked {d} – call before you go'", LJ)
        self.assertIn("unv:'Unverified – call before you go'", LJ)
    def test_no_hardcoded_date_in_rule(self):
        import re
        rule = LJ[LJ.index("const HAS_T"):LJ.index("const tierTop")]
        self.assertIsNone(re.search(r"20\d\d-\d\d-\d\d", rule))

class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def test_rule(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            pg = b.new_page(); open_map(pg, f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"); pg.wait_for_timeout(1500)
            now = pg.evaluate("new Date('2026-10-25T12:00:00').getTime()")
            T = lambda i, n=now: pg.evaluate("([i,n])=>timesChecked(i,n)", [i, n])
            self.assertEqual(T({"times_status": "confirmed", "times_checked": "2026-10-25"}), "2026-10-25")
            self.assertEqual(T({"times_status": "updated", "times_checked": "2026-10-24"}), "2026-10-24")
            self.assertEqual(T({"times_status": "confirmed_by_hand", "times_checked": "2026-10-20"}), "2026-10-20")
            self.assertIsNone(T({"times_status": "unconfirmed", "times_checked": "2026-10-25"}))
            self.assertIsNone(T({"hours": "By referral, call to arrange", "hours_checked": "2026-10-23"}))
            self.assertEqual(T({"hours": "Open 24 hours", "hours_checked": "2026-10-23"}), "2026-10-23")
            self.assertEqual(T({"hours": {"Mon": "11:00 - 15:00"}, "hours_checked": "2026-10-23"}), "2026-10-23")
            self.assertIsNone(T({"hours": {"Mon": "Open (times not published, call first)"}, "hours_checked": "2026-10-23"}))
            # rolling window: same item drops back to Unverified after 7 days, with no code change
            self.assertIsNone(T({"times_status": "confirmed", "times_checked": "2026-10-25"}, now + 9 * DAY))
            self.assertEqual(T({"times_status": "confirmed", "times_checked": "2026-10-25"}, now + 6 * DAY), "2026-10-25")
            # rendered card text
            html = pg.evaluate("()=>{const i=(window.WARMSPACES||{items:[]}).items.find(x=>x.tier==='unverified'&&timesChecked(x));return i?tierTop(i):null}")
            if html: self.assertIn("Times checked", html); self.assertNotIn("Unverified", html)
            b.close()
