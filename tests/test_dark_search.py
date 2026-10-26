"""owner 26 Oct 06:46: in dark mode the postcode box is a dark field with light text, a readable placeholder
and a gold focus outline. Its size, font and layout match light mode. Map tiles stay the light tiles
(no darken, invert or recolour). Call 999 is covered by tests/test_dark_shelter_panel.py."""
import functools, http.server, os, sys, threading, unittest
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
R = os.path.join(os.path.dirname(__file__), '..')
CH = '/usr/bin/google-chrome'
try:
    import playwright
    HAVE = os.path.exists(CH)
except Exception:
    HAVE = False

def lum(rgb):
    v = [int(x) / 255 for x in rgb.replace('rgba(', '').replace('rgb(', '').rstrip(')').split(',')[:3]]
    v = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

MEASURE = r"""()=>{const q=document.getElementById('q');q.focus();
 const cs=getComputedStyle(q),ph=getComputedStyle(q,'::placeholder'),r=q.getBoundingClientRect();
 const map=document.getElementById('map'),tile=document.querySelector('#map .leaflet-tile-pane')||map;
 const hh=document.querySelector('header').getBoundingClientRect().height;
 return {bg:cs.backgroundColor,color:cs.color,ph:ph.color,font:cs.fontSize,family:cs.fontFamily,
  h:r.height,w:r.width,pad:cs.padding,radius:cs.borderRadius,lh:cs.lineHeight,
  outline:[cs.outlineWidth,cs.outlineStyle,cs.outlineColor],
  map:getComputedStyle(map).filter,tile:getComputedStyle(tile).filter,hh}}"""

class T(unittest.TestCase):
    def test_tiles_stay_a_light_style(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertIn('streets-v2', tiles)
        self.assertIn('osm_bright', tiles)
        self.assertNotIn('dark-matter', tiles)
        for rel in ('header.css', 'v3.css', 'layers.css', 'index.html'):
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            self.assertNotIn('invert(', text, rel)
            self.assertNotRegex(text, r'leaflet-tile[^}{]*filter\s*:\s*(?!none)', rel)

    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_dark_field_same_box(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
        h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for w in (390, 1366):
                    got = {}
                    for mode in ('dark', 'light'):
                        c = b.new_context(viewport={'width': w, 'height': 844}, color_scheme=mode, service_workers='block')
                        c.add_init_script("try{localStorage.setItem('light','%s')}catch(e){}" % ('1' if mode == 'light' else '0'))
                        pg = c.new_page()
                        open_map(pg, 'http://127.0.0.1:%d/?nocount' % s.server_address[1])
                        pg.evaluate("m=>document.documentElement.classList.toggle('light', m==='light')", mode)
                        got[mode] = pg.evaluate(MEASURE)
                        c.close()
                    d, L = got['dark'], got['light']
                    if lum(d['bg']) > 0.2: bad.append((w, 'dark field is still light', d['bg']))
                    if lum(d['color']) < 0.7: bad.append((w, 'dark field text is not light', d['color']))
                    if ratio(d['bg'], d['color']) < 7: bad.append((w, 'text contrast', d['bg'], d['color'], ratio(d['bg'], d['color'])))
                    if ratio(d['bg'], d['ph']) < 4.5: bad.append((w, 'placeholder contrast', d['bg'], d['ph'], ratio(d['bg'], d['ph'])))
                    if d['outline'][1] == 'none' or d['outline'][2] != 'rgb(245, 197, 24)': bad.append((w, 'focus outline', d['outline']))
                    if float(d['outline'][0].replace('px', '') or 0) < 2: bad.append((w, 'focus outline thin', d['outline']))
                    if lum(L['bg']) < 0.8: bad.append((w, 'light mode field went dark', L['bg']))
                    for key in ('font', 'family', 'pad', 'radius', 'lh'):
                        if d[key] != L[key]: bad.append((w, key, d[key], L[key]))
                    if abs(d['h'] - L['h']) > 0.5 or abs(d['w'] - L['w']) > 1: bad.append((w, 'box', d['h'], L['h'], d['w'], L['w']))
                    if abs(d['hh'] - L['hh']) > 0.5: bad.append((w, 'header height', d['hh'], L['hh']))
                    for mode, row in got.items():
                        if row['map'] != 'none' or row['tile'] != 'none': bad.append((w, mode, 'map filter', row['map'], row['tile']))
                b.close()
        finally:
            s.shutdown()
        self.assertEqual(bad, [])

if __name__ == '__main__':
    unittest.main()
