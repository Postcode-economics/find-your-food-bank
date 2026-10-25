"""One Open today control and one note for all three lists (Dean, 25 Oct 2026 07:18); 'Verified only' hides exactly
the cards labelled 'Unverified – call before you go'."""
import os, json, unittest, threading, functools, http.server
ROOT = os.path.join(os.path.dirname(__file__), "..")
LJ = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()

class Static(unittest.TestCase):
    def test_no_per_layer_open_now(self):
        for s in ("Open now only", "Open now first. Closed places hidden.", "Ar agor nawr yn unig"):
            self.assertNotIn(s, LJ)

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
    def test_lists(self):
        from playwright.sync_api import sync_playwright
        base = f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            pg = b.new_page(viewport={"width": 390, "height": 844}); pg.goto(base, wait_until="networkidle"); pg.wait_for_timeout(1500)
            for k in ("fb", "ws", "sh"):
                pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1000)
                for on in (False, True):
                    if pg.evaluate("document.getElementById('openToday').checked") != on: pg.click("#v3open"); pg.wait_for_timeout(300)
                    pg.evaluate("()=>nearest(51.5074,-0.1278,'London')"); pg.wait_for_timeout(600)
                    r = pg.evaluate("""()=>({notes:[...document.querySelectorAll('.tnote,.v3ex')].filter(e=>!e.hidden&&e.offsetParent!==null).map(e=>e.textContent),
                        oo:document.querySelectorAll('.v3oo').length})""")
                    self.assertEqual(r["oo"], 0, k)
                    heads = pg.evaluate("()=>[...document.querySelectorAll('#list>.lh,#xlist>.lh')].filter(e=>e.offsetParent!==null).map(e=>e.textContent)")
                    self.assertTrue(heads and all("(open today first)" not in h for h in heads), (k, on, heads))
                    self.assertEqual(pg.evaluate("(document.getElementById('hid')||{}).textContent||''"), '', k)  # no counts line
                    self.assertEqual(r["notes"], ["Showing places open today. If no times are listed, call before you go."] if on else [], (k, on))
            for k in ("ws", "sh"):
                pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1000)
                if pg.evaluate("document.getElementById('openToday').checked"): pg.click("#v3open"); pg.wait_for_timeout(300)
                for lat, lng in ((51.5074, -0.1278), (53.4808, -2.2426), (55.8642, -4.2518)):
                    pg.evaluate("([a,b])=>nearest(a,b,'t')", [lat, lng]); pg.wait_for_timeout(400)
                    if pg.evaluate(f"document.querySelector('.v3vo[data-k={k}]').getAttribute('aria-pressed')") != "true": pg.click(f".v3vo[data-k={k}]"); pg.wait_for_timeout(400)
                    labs = pg.evaluate(f"()=>[...document.querySelectorAll('#xlist .card.x{k} .xunv')].map(e=>e.textContent)")
                    self.assertFalse(any(l.startswith("Unverified") for l in labs), (k, labs))
                    pg.click(f".v3vo[data-k={k}]"); pg.wait_for_timeout(400)
            b.close()

class Strings(unittest.TestCase):
    def test_no_duplicate_keys(self):
        import re, collections
        s = LJ; en = s[s.index("const T={en:{"):s.index("cy:{")]; cy = s[s.index("cy:{"):s.index("}}", s.index("cy:{"))]
        for b in (en, cy):
            c = collections.Counter(re.findall(r"[{,](\w+):'", b)); self.assertEqual([k for k, v in c.items() if v > 1], [])
    def test_card_checked_label(self):
        self.assertIn("chk:'Checked'", LJ); self.assertIn("chkL:'Listings last checked '", LJ)
