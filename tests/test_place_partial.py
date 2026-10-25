"""'Suffolk' silently jumped to Suffolk Hill, Dumfries (live sweep, 25 Oct 2026): a place search that isn't an exact
name match is offered as a button, never assumed. Exact names still go straight to the list."""
import os, json, unittest, threading, functools, http.server
ROOT = os.path.join(os.path.dirname(__file__), "..")
SH = {"status": 200, "result": [{"name_1": "Suffolk Hill", "local_type": "Suburban Area", "county_unitary": "Dumfries and Galloway", "country": "Scotland", "latitude": 55.07, "longitude": -3.6}]}
LH = {"status": 200, "result": [{"name_1": "Littlehampton", "local_type": "Town", "county_unitary": "West Sussex", "country": "England", "latitude": 50.81, "longitude": -0.54}]}
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception: raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def test_partial_offered(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            c.route("https://api.postcodes.io/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(LH if "Littlehampton" in r.request.url else SH if "places" in r.request.url else {"status": 404})))
            pg = c.new_page(); pg.goto(f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1", wait_until="networkidle"); pg.wait_for_timeout(1200)
            pg.fill("#q", "Suffolk"); pg.press("#q", "Enter"); pg.wait_for_timeout(1500)
            self.assertIn("couldn’t find a town called “Suffolk”", pg.inner_text(".v3err"))
            self.assertEqual(pg.locator("#list>.card").count(), 0)
            self.assertTrue(pg.locator(".didyou").is_visible())
            pg.click(".didyou"); pg.wait_for_timeout(1500)
            self.assertGreater(pg.locator("#list>.card").count(), 0); self.assertIn("Suffolk Hill", pg.inner_text("#list"))
            pg.fill("#q", "Littlehampton"); pg.press("#q", "Enter"); pg.wait_for_timeout(1500)
            self.assertIn("Littlehampton", pg.inner_text("#list"))
            c.close(); b.close()
