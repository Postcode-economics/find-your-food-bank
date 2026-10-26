"""Live bug 25 Oct 2026 (v86): a '//' comment swallowed 'let lastNear=null;', so every filter change threw
'lastNear is not defined' before saving - Open today looked stuck and its state was not kept. Real taps, all three types,
phone + desktop: no page errors, Open today turns on AND off, the choice is saved and restored on reload; the ✕ collapses
and the Filters tab reopens."""
import functools, http.server, os, sys, threading, unittest
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map, reload_map
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
import importlib.util; HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None  # CI 'test' job has Chrome but no playwright
@unittest.skipUnless(HAVE, 'needs chrome + playwright')
class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        cls.s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=cls.s.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:%d/?nocount' % cls.s.server_address[1]
    @classmethod
    def tearDownClass(cls): cls.s.shutdown()
    def test_toggle_save_reload_and_x(self):
        from playwright.sync_api import sync_playwright
        S = "[document.getElementById('openToday').checked, JSON.parse(localStorage.getItem('fbFilters')||'{\"f\":{}}').f.open||false]"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CH)
            for w in (390, 1366):
                for k in ('fb', 'ws', 'sh'):
                    kw = dict(viewport={'width': w, 'height': 844}, service_workers='block')
                    if w < 800: kw.update(has_touch=True, is_mobile=True)
                    c = b.new_context(**kw); pg = c.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
                    open_map(pg, self.base); pg.wait_for_timeout(1000)
                    pg.evaluate("k=>{const t=[...document.querySelectorAll('#v3big button,#v3big [role=radio]')].find(b=>(b.dataset.k||b.dataset.l||b.dataset.layer)===k);if(t)t.click()}", k)
                    pg.fill('#q', 'Croydon'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2500); pg.evaluate('scrollTo(0,0)')
                    tap = (lambda: pg.locator('#v3open').tap()) if w < 800 else (lambda: pg.locator('#v3open').click())
                    tap(); pg.wait_for_timeout(500); self.assertEqual(pg.evaluate(S), [True, True], (w, k, 'on'))
                    reload_map(pg); pg.wait_for_timeout(1200); self.assertEqual(pg.evaluate(S), [True, True], (w, k, 'reload on'))
                    pg.evaluate('scrollTo(0,0)'); tap(); pg.wait_for_timeout(500); self.assertEqual(pg.evaluate(S), [False, False], (w, k, 'off'))
                    reload_map(pg); pg.wait_for_timeout(1200); self.assertEqual(pg.evaluate(S), [False, False], (w, k, 'reload off'))
                    pg.evaluate('scrollTo(0,0)'); print('X', w, k, pg.evaluate("(()=>{const x=document.getElementById('fhide');let e=x,i=[];while(e){if(e.inert)i.push(e.id||e.tagName);e=e.parentElement}return [x.disabled,i,!!x.offsetParent]})()")); pg.click('#fhide', timeout=5000); pg.wait_for_timeout(400)
                    self.assertTrue(pg.evaluate("document.getElementById('v3filt').classList.contains('fclosed')&&!!document.getElementById('ftab').offsetParent"), (w, k, 'x collapses'))
                    pg.click('#ftab'); pg.wait_for_timeout(400)
                    self.assertTrue(pg.evaluate("!document.getElementById('v3filt').classList.contains('fclosed')&&!!document.querySelector('#v3filt [data-f=walk]').offsetParent"), (w, k, 'tab reopens'))
                    self.assertEqual(errs, [], (w, k)); c.close()
            b.close()
    def test_no_comment_swallows_code(self):
        """Guard for the v86 bug: a '//' comment directly followed (same line) by a declaration that later code needs."""
        import re
        h = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        self.assertEqual(re.findall(r'//[^\n]*[a-z](?:let|const) [A-Za-z_$]+=', h), [])
        self.assertIn('\nlet lastNear=null;', h)
    def test_x_never_inert(self):
        s = open(os.path.join(R, 'v3.js'), encoding='utf-8').read()
        self.assertNotIn("['fwrap','ftab'].forEach(id=>{const e=document.getElementById(id);if(!e)return;e.classList.toggle('v3off'", s)
