"""'Find nearest' button follows the selected type (Dean, 23 Oct 2026)."""
import os, re, unittest, threading, functools, http.server
ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()

class Static(unittest.TestCase):
    def test_labels_per_type(self):
        for s in ("Find nearest food bank", "Find nearest shelter", "Find nearest warm space"):
            self.assertIn(s, SRC)
    def test_no_type_keeps_food_bank_default(self):
        self.assertIn("k?NL[lang][k]:t('near')", SRC)          # no type -> original label
        self.assertIn("window.__nearK=k==='sh'||k==='ws'?k:null", SRC)  # food bank / none -> old behaviour
    def test_still_uses_location_button(self):
        self.assertIn("document.getElementById('me').click()", SRC)

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
    def test_follows_type(self):
        from playwright.sync_api import sync_playwright
        base = f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for k, lab, head in (("sh", "Find nearest shelter", "Nearest shelters"), ("ws", "Find nearest warm space", "Nearest warm spaces"), ("fb", "Find nearest food bank", None)):
                c = b.new_context(viewport={"width": 390, "height": 844}, geolocation={"latitude": 51.539, "longitude": -0.1426}, permissions=["geolocation"])
                pg = c.new_page(); pg.goto(base, wait_until="networkidle"); pg.wait_for_timeout(1500)
                pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1200)
                self.assertEqual(pg.locator("#xnear").inner_text().strip(), lab)
                pg.click("#xnear"); pg.wait_for_timeout(3500)
                if head:
                    top = pg.evaluate("(h=>{const e=[...document.querySelectorAll('#xlist .lh')].find(x=>x.textContent===h);return e?e.getBoundingClientRect().top:null})", head)
                    self.assertIsNotNone(top); self.assertTrue(0 <= top < 844 * 0.5, top)
                    tels = pg.evaluate("[...document.querySelectorAll('#xlist .card')].map(c=>[...c.querySelectorAll('a[href^=\"tel:\"]')].some(a=>!/tel:(999|0808|116)/.test(a.getAttribute('href'))))")
                    self.assertTrue(tels and all(tels), tels)
                else:
                    top = pg.evaluate("document.querySelector('#list .card').getBoundingClientRect().top")
                    self.assertTrue(0 <= top < 844, top)
                c.close()
            b.close()

if __name__ == "__main__": unittest.main()
