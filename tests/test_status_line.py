"""Header status line (14 Nov 2026, Dean): the 'Food banks near you' / 'Food banks near <place>' (and Warm spaces /
Shelters, plus Welsh) text under the yellow Find nearest bar must not show after a search. Header height stays
the same across searches and layers at 320, 360, 390 and 1366 px, light and dark. Errors still use the reserved slot."""
import functools, http.server, importlib.util, os, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
CHECK = r"""()=>{
 const prow=document.getElementById('v3prow'), pill=document.getElementById('v3pill'), pl=document.querySelector('#v3pill .v3pl');
 const vis=e=>!!(e && e.offsetParent && getComputedStyle(e).display!=='none' && e.getBoundingClientRect().height>1);
 const placeOn=vis(prow)||vis(pl);
 const errOn=!!(pill&&pill.querySelector('.v3err,.didyou')&&vis(pill));
 const _hdr=document.querySelector('header').getBoundingClientRect();const _ban=document.getElementById('em-banner');
 let hh=_hdr.height;if(_ban&&!_ban.hidden){const br=_ban.getBoundingClientRect();if(br.height>1){const cs=getComputedStyle(_ban);hh-=br.height+(parseFloat(cs.marginTop)||0)+(parseFloat(cs.marginBottom)||0)}}
 const cards=(document.querySelectorAll('#list .card,#xlist .card').length);
 return {ok:!placeOn, placeOn, errOn, cards, hh, why: placeOn?'place line still visible':'hidden', text:(pl&&pl.textContent)||''}}"""
class T(unittest.TestCase):
    def test_static(self):
        s = open(os.path.join(R, 'v3.js'), encoding='utf-8').read()
        self.assertIn('near you', s); self.assertNotIn('see list ↓', s)
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_never_clipped(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for w in (320, 360, 390, 1366):
                    for mode in ('light', 'dark'):
                        c = b.new_context(viewport={'width': w, 'height': 800}, color_scheme=mode, service_workers='block'); pg = c.new_page()
                        open_map(pg, 'http://127.0.0.1:%d/?nocount' % s.server_address[1]); pg.wait_for_timeout(800)
                        pg.evaluate("m=>document.documentElement.classList.toggle('light',m==='light')", mode)
                        for k in ('fb', 'ws', 'sh'):
                            pg.evaluate("k=>{const t=document.querySelector('#v3big [data-l='+k+']');if(t)t.click()}", k)
                            ref = None
                            for q in ('Croydon', 'BN17 5LF', 'Newcastle-under-Lyme', 'Llanfair Pwllgwyngyll', 'Bradford-on-Avon', 'Bournemouth, Christchurch and Poole'):
                                pg.fill('#q', q); pg.press('#q', 'Enter'); pg.wait_for_timeout(2200)
                                r = pg.evaluate(CHECK)
                                for _ in range(12):
                                    if r.get('cards', 0) > 0 or r.get('errOn'): break
                                    pg.wait_for_timeout(1000); r = pg.evaluate(CHECK)
                                if ref is None: ref = r.get('hh')
                                elif abs(r.get('hh', 0) - ref) > 0.5: bad.append((w, mode, k, q, 'header height %s != %s' % (r.get('hh'), ref)))
                                if r.get('placeOn'): bad.append((w, mode, k, q, 'place line still visible: ' + (r.get('text') or '')))
                        c.close()
                b.close()
        finally: s.shutdown()
        with tempfile.TemporaryDirectory() as directory:
            import json
            with open(os.path.join(directory, 'status_line_bad.json'), 'w') as output:
                json.dump(bad, output, indent=1)
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()

def real_names():
    """Longest names our search can return: ONS counties/unitary areas (English + Welsh), area-page names, plus long real
    places the postcodes.io place search returns (that source cannot be listed in full, so known long ones are added)."""
    import json, glob, re, html
    n = set()
    for a in json.load(open(os.path.join(R, 'counties.json')))['areas']:
        n.add(a['name']); a.get('name_cy') and n.add(a['name_cy'])
    for f in glob.glob(os.path.join(R, '*', '*', 'index.html')):
        if os.path.basename(os.path.dirname(os.path.dirname(f))) in ('food-banks', 'warm-spaces', 'shelters'):
            m = re.search(r'<h1[^>]*>(.*?)</h1>', open(f, encoding='utf-8').read(), re.S)
            if m: n.add(re.sub(r'^(Food banks|Warm spaces|Homeless shelters) in ', '', html.unescape(re.sub(r'<[^>]+>', '', m.group(1)).strip())))
    n |= {'Llanfairpwllgwyngyll', 'Newcastle-under-Lyme', 'Bradford-on-Avon', 'Sutton-under-Whitestonecliffe', 'Kirkby-in-Ashfield',
          'Llanfair Pwllgwyngyll', 'Stow-on-the-Wold', 'Westward Ho!'}
    return sorted(n, key=len, reverse=True)

class LongestNames(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_place_line_hidden_after_search_at_320(self):
        """14 Nov 2026 (Dean): the place line under the yellow bar must not show after a search, including at 320px."""
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH); pg = b.new_page(viewport={'width': 320, 'height': 800}, service_workers='block')
                open_map(pg, 'http://127.0.0.1:%d/?nocount' % s.server_address[1]); pg.wait_for_timeout(800)
                pg.fill('#q', 'Croydon'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2500)
                r = pg.evaluate(CHECK)
                for _ in range(12):
                    if r.get('cards', 0) > 0: break
                    pg.wait_for_timeout(1000); r = pg.evaluate(CHECK)
                b.close()
        finally: s.shutdown()
        self.assertFalse(r.get('placeOn'), r)
        self.assertGreater(r.get('cards', 0), 0, r)

class ShortNames(unittest.TestCase):
    def test_mapping_present(self):
        src = open(os.path.join(R, 'v3.js'), encoding='utf-8').read()
        self.assertIn("'Armagh City, Banbridge and Craigavon':'Craigavon'", src)
        self.assertIn("'Bournemouth, Christchurch and Poole':'Bournemouth'", src)
        self.assertIn("lb=v3short(lb)", src)
