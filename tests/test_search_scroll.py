"""Search/Enter follows the selected type (Dean, 25 Oct 2026): with Warm spaces or Shelters selected,
an explicit search lands on that list, not the food bank cards. Food banks / no type: unchanged."""
import os, json, unittest, threading, functools, http.server
ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
PC = {"status": 200, "result": {"postcode": "BN17 5LF", "latitude": 50.8095, "longitude": -0.5405}}

class Static(unittest.TestCase):
    def test_submit_sets_type(self):
        self.assertIn("{const k=window.v3focus;window.__nearK=(k==='sh'||k==='ws')?k:null}search($('q').value)", SRC)

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
    def test_search_lands_on_selected_list(self):
        from playwright.sync_api import sync_playwright
        base = f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for w in (390, 1366):
                for k, head in (("ws", "Nearest warm spaces"), ("sh", "Nearest shelters"), ("fb", None)):
                    for how in ("enter", "button"):
                        c = b.new_context(viewport={"width": w, "height": 844}, service_workers="block")
                        c.route("https://api.postcodes.io/**", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(PC)))
                        pg = c.new_page(); pg.goto(base, wait_until="networkidle"); pg.wait_for_timeout(1500)
                        pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1000)
                        pg.fill("#q", "BN17 5LF")
                        if how == "enter": pg.press("#q", "Enter")
                        else: pg.evaluate("()=>document.getElementById('f').requestSubmit()")
                        pg.wait_for_timeout(3000)
                        if head:
                            top = pg.evaluate("h=>{const e=[...document.querySelectorAll('#xlist .lh')].find(x=>x.textContent===h);return e?e.getBoundingClientRect().top/innerHeight:null}", head)
                            self.assertIsNotNone(top, (w, k, how)); self.assertTrue(0 <= top <= 0.4, (w, k, how, top))
                        else:
                            top = pg.evaluate("()=>{const e=document.querySelector('#list .card');return e?e.getBoundingClientRect().top/innerHeight:null}")
                            self.assertIsNotNone(top); self.assertTrue(0 <= top <= 0.85, (w, how, top))
                        c.close()
            b.close()
