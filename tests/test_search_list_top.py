"""Search lands exactly where the 'see list' pill does (Dean, 25 Oct 2026, 07:04): one shared scroll for
food banks, warm spaces and shelters; the list heading sits at the top with no map visible above it."""
import os, json, sys, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.join(os.path.dirname(__file__), "..")
PC = {"status": 200, "result": {"postcode": "BN17 5LF", "latitude": 50.8095, "longitude": -0.5405}}
POS = """k=>{const t=document.getElementById(k==='fb'?'list':'xlist');const s=document.getElementById('v3sos');
 const h=(k==='sh'&&s&&!s.hidden)?s:(t.querySelector('.lh')||t);const m=document.getElementById('map').getBoundingClientRect();
 const r=h.getBoundingClientRect();return {top:r.top,mapBottom:m.bottom,overlap:m.left<r.right&&r.left<m.right}}"""

class Static(unittest.TestCase):
    def test_one_shared_scroll(self):
        v3 = open(os.path.join(ROOT, "v3.js"), encoding="utf-8").read(); ix = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn("window.v3scrollList=scrollList", v3); self.assertIn("scrollList(window.v3focus);", v3)
        self.assertIn("if(go&&window.v3scrollList){setTimeout(()=>v3scrollList(window.v3focus),0)}", ix)

class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def test_search_matches_pill(self):
        from playwright.sync_api import sync_playwright
        base = f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for w in (390, 1366):
                for k in ("fb", "ws", "sh"):
                    c = b.new_context(viewport={"width": w, "height": 844}, service_workers="block", reduced_motion="reduce")
                    c.route("https://api.postcodes.io/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(PC)))
                    pg = c.new_page(); open_map(pg, base); pg.wait_for_timeout(1500)
                    pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1000)
                    pg.fill("#q", "BN17 5LF"); pg.press("#q", "Enter"); pg.wait_for_timeout(3500)
                    a = pg.evaluate(POS, k)
                    pg.evaluate("scrollTo(0,0)"); pg.wait_for_timeout(300)
                    pg.click("a.v3pl"); pg.wait_for_timeout(1200)
                    bpos = pg.evaluate(POS, k)
                    self.assertLessEqual(abs(a["top"] - bpos["top"]), 4, (w, k, a, bpos))
                    self.assertTrue(0 <= a["top"] <= 30, (w, k, a))
                    if a["overlap"]: self.assertLessEqual(a["mapBottom"], max(0, a["top"]), (w, k, a))  # map above the list (phone): none visible; desktop map sits beside the list
                    c.close()
            b.close()
