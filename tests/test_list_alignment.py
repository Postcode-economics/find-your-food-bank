"""List panel alignment (Dean 25 Oct 14:06): the Open today note, other notes, headings and cards all start at the same
left x, on all three types, at 390 and 1366 px, light and dark."""
import functools, http.server, importlib.util, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
JS = """k=>{const root=k==='fb'?document.getElementById('list'):document.getElementById('xlist');const panel=root.parentElement;
 const els=[...panel.querySelectorAll('.tnote,.lh,.card,#v3res > *')].filter(e=>e.offsetParent&&e.getClientRects().length&&!e.parentElement.closest('.card')&&e.textContent.trim());
 return els.map(e=>{const r=document.createRange();r.selectNodeContents(e);const t=[...r.getClientRects()].filter(x=>x.width>0)[0];
   const cs=getComputedStyle(e);const pad=e.classList.contains('card')?0:0;return [e.className.toString().slice(0,20)||e.id,Math.round(e.classList.contains('card')?e.getBoundingClientRect().left:(t?t.left:e.getBoundingClientRect().left)),e.textContent.trim().slice(0,30)]})}"""
class T(unittest.TestCase):
    def test_static(self):
        self.assertIn('.tnote{margin-left:0!important', open(os.path.join(R, 'header.css')).read())
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_same_left_edge(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for w in (390, 1366):
                    for mode in ('light', 'dark'):
                        c = b.new_context(viewport={'width': w, 'height': 900}, color_scheme=mode, service_workers='block'); pg = c.new_page()
                        pg.goto('http://127.0.0.1:%d/?nocount' % s.server_address[1], wait_until='networkidle'); pg.wait_for_timeout(800)
                        pg.evaluate("m=>document.documentElement.classList.toggle('light',m==='light')", mode)
                        for k in ('fb', 'ws', 'sh'):
                            pg.evaluate("k=>{const t=document.querySelector('#v3big [data-l='+k+']');if(t)t.click()}", k); pg.wait_for_timeout(400)
                            for on in (True, False):
                                pg.evaluate("on=>{const o=document.getElementById('openToday');if(o.checked!==on)o.click()}", on)
                                pg.fill('#q', 'Croydon'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2300)
                                r = pg.evaluate(JS, k); xs = {x for _, x, _ in r}
                                if len(r) < 2 or max(xs) - min(xs) > 1: bad.append((w, mode, k, on, r[:6]))
                        c.close()
                b.close()
        finally: s.shutdown()
        self.assertEqual(bad, [])
