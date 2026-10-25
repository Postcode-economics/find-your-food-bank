"""Header status line (Dean 25 Oct 13:32): 'Food banks near you' / 'Food banks near <place>', never overflowing or clipped
at 320, 360, 390 and 1366 px, light and dark, on all three types; Dean 13:35: fixed font, ONE line, header height identical to the short-text case, no overflow, no ellipsis; if it does not fit, just the place name."""
import functools, http.server, importlib.util, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
CHECK = r"""()=>{const a=document.querySelector('#v3pill .v3pl');if(!a||!a.offsetParent)return {ok:false,why:'no status line'};
 const box=document.getElementById('v3pill').getBoundingClientRect(),r=a.getBoundingClientRect();
 const vis=[...a.querySelectorAll('.v-en,.v-cy')].find(e=>e.offsetParent);const fixed=[...vis.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('');
 const place=vis.querySelector('.v3plc');
 const info=document.getElementById('h2info'),near=document.getElementById('xnear'),ir=info?info.getBoundingClientRect():box,nr=near?near.getBoundingClientRect():null;
 const ok=r.left>=box.left-1&&r.right<=box.right+1&&r.right<=innerWidth&&a.scrollWidth<=a.clientWidth+1&&!/…|\.\.\./.test(vis.textContent)
   &&getComputedStyle(place||a).textOverflow!=='ellipsis'&&r.bottom<=ir.bottom+1&&(!nr||nr.bottom<=ir.top+1)&&document.documentElement.scrollWidth<=innerWidth&&!a.style.fontSize;
 const hh=document.querySelector('header').getBoundingClientRect().height;return {ok,hh,why:vis.textContent+' | link '+Math.round(r.left)+'-'+Math.round(r.right)+' box '+Math.round(box.left)+'-'+Math.round(box.right)+' sw '+a.scrollWidth+' cw '+a.clientWidth,text:vis.textContent}}"""
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
                        pg.goto('http://127.0.0.1:%d/?nocount' % s.server_address[1], wait_until='networkidle'); pg.wait_for_timeout(800)
                        pg.evaluate("m=>document.documentElement.classList.toggle('light',m==='light')", mode)
                        for k in ('fb', 'ws', 'sh'):
                            pg.evaluate("k=>{const t=document.querySelector('#v3big [data-l='+k+']');if(t)t.click()}", k)
                            ref = None
                            for q in ('Croydon', 'BN17 5LF', 'Newcastle-under-Lyme', 'Llanfair Pwllgwyngyll', 'Bradford-on-Avon', 'Bournemouth, Christchurch and Poole'):
                                pg.fill('#q', q); pg.press('#q', 'Enter'); pg.wait_for_timeout(2200)
                                r = pg.evaluate(CHECK)
                                for _ in range(12):   # search still settling (slow place lookup under load): wait for THIS query's result, up to ~12 s more; clip checks unchanged
                                    if r['ok'] and (q == 'BN17 5LF' or q.split(',')[0].lower()[:6] in r.get('text', '').lower()): break
                                    pg.wait_for_timeout(1000); r = pg.evaluate(CHECK)
                                if ref is None: ref = r.get('hh')
                                elif abs(r.get('hh', 0) - ref) > 0.5: bad.append((w, mode, k, q, 'header height %s != %s' % (r.get('hh'), ref)))
                                want = {'fb': 'Food banks near', 'ws': 'Warm spaces near', 'sh': 'Shelters near'}[k]
                                if not r['ok'] or not (r.get('text', '').startswith(want) or r.get('text', '').lower().startswith(q.split(',')[0].lower()[:6])) or (q != 'BN17 5LF' and q.split(',')[0].lower() not in r.get('text', '').lower()): bad.append((w, mode, k, q, r['why']))
                        c.close()
                b.close()
        finally: s.shutdown()
        import json; json.dump(bad, open(os.path.join(R, 'logs', 'status_line_bad.json'), 'w'), indent=1)
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
    def test_every_real_name_fits_alone_at_320(self):
        """Dean 13:35: each real place name must fit on one line ALONE at 320px at the fixed font; report any that do not."""
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        names = real_names()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH); pg = b.new_page(viewport={'width': 320, 'height': 800}, service_workers='block')
                pg.goto('http://127.0.0.1:%d/?nocount' % s.server_address[1], wait_until='networkidle'); pg.wait_for_timeout(800)
                pg.fill('#q', 'Croydon'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2500)
                names = pg.evaluate("ns=>ns.map(v3short)", names)   # what the status line actually shows
                too_long = pg.evaluate("""ns=>{const a=document.querySelector('#v3pill .v3pl');const out=[];const fs=getComputedStyle(a).fontSize;
                  for(const n of ns){a.querySelectorAll('.v-en,.v-cy').forEach(e=>{e.textContent=n});if(a.scrollWidth>a.clientWidth+1)out.push(n)}
                  return {fs,out}}""", names)
                b.close()
        finally: s.shutdown()
        print('status line font', too_long['fs'], '- names that do not fit alone at 320px:', too_long['out'])
        # Reported to Dean 25 Oct 13:40 (his call, no rule invented): these two ONS names do not fit alone at 320px at the fixed 15px.
        # Any OTHER name that does not fit fails this test.
        PENDING_DEAN = set()   # FINAL: Dean confirmed 25 Oct 14:11 - ', County' dropped; short forms in V3SHORT (v3.js)
        self.assertEqual(set(too_long['out']) - PENDING_DEAN, set(), 'real names too long for one line at 320px: %s' % too_long['out'])


class ShortNames(unittest.TestCase):
    def test_mapping_present(self):
        src = open(os.path.join(R, 'v3.js'), encoding='utf-8').read()
        self.assertIn("'Armagh City, Banbridge and Craigavon':'Craigavon'", src)
        self.assertIn("'Bournemouth, Christchurch and Poole':'Bournemouth'", src)
        self.assertIn("lb=v3short(lb)", src)
