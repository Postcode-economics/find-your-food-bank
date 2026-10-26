"""Touch map gestures (Dean, 25 Oct 2026, 07:42): on touch devices one finger over the map scrolls the page and shows
'Use two fingers to move the map'; two fingers pan/zoom; marker taps and +/- still work. Desktop unchanged."""
import os, sys, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.join(os.path.dirname(__file__), "..")
SHOT = os.environ.get("TOUCH_SHOT")

class Static(unittest.TestCase):
    def test_code(self):
        ix = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn("matchMedia('(hover:none) and (pointer:coarse)')", ix); self.assertIn("map.dragging.disable()", ix)
        self.assertIn("Use two fingers to move the map", ix); self.assertIn("Defnyddiwch ddau fys i symud y map", ix)

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
    def base(self): return f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"

    def test_touch(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for scheme in ("light", "dark"):
                c = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, color_scheme=scheme, service_workers="block")
                pg = c.new_page(); open_map(pg, self.base()); pg.wait_for_timeout(1500)
                pg.evaluate("()=>{map.setView([50.81,-0.54],13,{animate:false})}"); pg.wait_for_timeout(800)
                self.assertFalse(pg.evaluate("map.dragging.enabled()"))
                r = pg.evaluate("(()=>{const r=map.getContainer().getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
                pg.evaluate("scrollTo(0,0)"); cdp = c.new_cdp_session(pg)
                c0 = pg.evaluate("[map.getCenter().lat,map.getCenter().lng]"); y0 = pg.evaluate("scrollY")
                T = lambda t, pts: cdp.send("Input.dispatchTouchEvent", {"type": t, "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})
                T("touchStart", [(r["x"], r["y"])])
                for d in range(1, 11): T("touchMove", [(r["x"], r["y"] - 15 * d)]); pg.wait_for_timeout(16)
                on = pg.evaluate("!!document.querySelector('.mgest.on')")
                if SHOT: pg.screenshot(path=f"{SHOT}_{scheme}.png")
                T("touchEnd", []); pg.wait_for_timeout(500)
                self.assertTrue(on, scheme)
                self.assertGreater(pg.evaluate("scrollY"), y0 + 50, scheme)  # page scrolled
                self.assertEqual(c0, pg.evaluate("[map.getCenter().lat,map.getCenter().lng]"), scheme)  # map did not move
                # two fingers: map pans, overlay hidden
                pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(300)
                r = pg.evaluate("(()=>{const r=map.getContainer().getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
                T("touchStart", [(r["x"] - 40, r["y"]), (r["x"] + 40, r["y"])])
                for d in range(1, 11): T("touchMove", [(r["x"] - 40 + 8 * d, r["y"] + 6 * d), (r["x"] + 40 + 8 * d, r["y"] + 6 * d)]); pg.wait_for_timeout(16)
                T("touchEnd", []); pg.wait_for_timeout(800)
                self.assertNotEqual(c0, pg.evaluate("[map.getCenter().lat,map.getCenter().lng]"), scheme)
                self.assertFalse(pg.evaluate("!!document.querySelector('.mgest.on')"))
                # +/- and marker tap with one finger
                z = pg.evaluate("map.getZoom()"); pg.tap(".leaflet-control-zoom-in"); pg.wait_for_timeout(600)
                self.assertEqual(pg.evaluate("map.getZoom()"), z + 1)
                pg.evaluate("()=>{map.setView([50.81,-0.54],15,{animate:false})}"); pg.wait_for_timeout(1000)
                m = pg.locator(".leaflet-marker-icon:not(.marker-cluster)").first; m.scroll_into_view_if_needed(); m.tap(); pg.wait_for_timeout(1000)
                self.assertIsNotNone(pg.evaluate("selected"), scheme)
                c.close()
            # desktop unchanged
            c = b.new_context(viewport={"width": 1366, "height": 900}, service_workers="block"); pg = c.new_page()
            open_map(pg, self.base()); pg.wait_for_timeout(1000)
            self.assertTrue(pg.evaluate("map.dragging.enabled()")); self.assertEqual(pg.locator(".mgest").count(), 0)
            self.assertFalse(pg.evaluate("map.scrollWheelZoom.enabled()")); pg.click("#map", position={"x": 300, "y": 150}); self.assertTrue(pg.evaluate("map.scrollWheelZoom.enabled()")); c.close()  # existing v3 desktop rule: wheel zoom after a click; b.close()
