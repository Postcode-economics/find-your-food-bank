"""Dean 25 Oct 17:05: first-time visitors get DARK whatever the phone setting; a saved light choice is kept; set before first paint."""
import functools, http.server, importlib.util, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
class T(unittest.TestCase):
    def test_static(self):
        h = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        self.assertLess(h.index("localStorage.getItem('light')==='1'"), h.index('<body'))
        self.assertNotIn("prefers-color-scheme: light)').matches", open(os.path.join(R, 'v3.js'), encoding='utf-8').read())
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_dark_default_and_saved_light_sw_off(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        u = 'http://127.0.0.1:%d/?nocount' % s.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for scheme in ('light', 'dark', 'no-preference'):
                    c = b.new_context(color_scheme=scheme, service_workers='block'); pg = c.new_page()  # sw_off: first visit, empty cache; Chromium, not iPhone WebKit
                    pg.goto(u, wait_until='domcontentloaded')
                    self.assertFalse(pg.evaluate("document.documentElement.classList.contains('light')"), scheme + ' first paint')
                    pg.wait_for_load_state('networkidle'); pg.wait_for_timeout(800)
                    self.assertFalse(pg.evaluate("document.documentElement.classList.contains('light')"), scheme + ' fresh visitor must be dark')
                    c.close()
                c = b.new_context(color_scheme='dark', service_workers='block')  # sw_off: first visit, empty cache; Chromium, not iPhone WebKit
                c.add_init_script("try{localStorage.setItem('light','1')}catch(e){}"); pg = c.new_page()
                seen = []
                pg.on('domcontentloaded', lambda: seen.append(pg.evaluate("document.documentElement.classList.contains('light')")))
                pg.goto(u, wait_until='networkidle'); pg.wait_for_timeout(800)
                self.assertTrue(pg.evaluate("document.documentElement.classList.contains('light')"), 'saved light kept')
                self.assertEqual(seen, [True], 'light set before first paint')
                b.close()
        finally: s.shutdown()
