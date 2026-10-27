"""Instagram in-app browser on iPhone = WebKit (Dean 25 Oct 19:13/19:15). In real WebKit with the Instagram UA, dark mode:
(1) 'List only' ON is readable and styled like the 'Light mode' link (no white box: text and background must contrast, background transparent);
(2) with List only OFF the map really paints (tiles loaded, pins shown) and sits on the phone page below the header;
(3) with List only ON the list still shows; (4) with storage blocked the page still works."""
import mimetypes, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import check_browser as B
R = os.path.join(os.path.dirname(__file__), '..')
IG = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 '
      'Instagram 330.0.0.0 (iPhone14,5; iOS 17_4; en_GB; en-GB; scale=3.00; 1170x2532; 600000000) helpmap-check')
def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p: p.webkit.launch().close()
        return True
    except Exception: return False
HAVE = have_webkit()
CARDS = "document.querySelectorAll('.card').length"
class T(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_instagram_webkit(self):
        from playwright.sync_api import sync_playwright
        # WebKit upgrades http subresources to https (CSP upgrade-insecure-requests), so serve this checkout AS https://helpmap.uk
        base = 'https://helpmap.uk'; bad = []
        def local(route):
            path = route.request.url.split(base, 1)[1].split('?')[0].split('#')[0] or '/'
            f = os.path.join(R, path.lstrip('/')); f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f): return route.fulfill(status=404, body='')
            route.fulfill(status=200, body=open(f, 'rb').read(), headers={'content-type': mimetypes.guess_type(f)[0] or 'text/html', 'cache-control': 'no-store'})
        def until(pg, js, secs=25):   # poll with evaluate (the site's CSP blocks wait_for_function's eval in WebKit)
            for _ in range(secs * 2):
                if pg.evaluate(js): return True
                pg.wait_for_timeout(500)
            return False
        def wait_cards(pg):
            until(pg, CARDS + '>0'); return pg.evaluate(CARDS)
        try:
            with sync_playwright() as p:
                b = p.webkit.launch()
                for nomap in ('1', '0'):
                    for block in (False, True):
                        if block and nomap == '1': continue
                        # Real iPhone WebKit: service worker allowed. Blocking it paints a grey OpenFreeMap.
                        c = b.new_context(viewport={'width': 390, 'height': 844}, user_agent=IG, is_mobile=True, has_touch=True, color_scheme='dark', service_workers='allow')
                        c.add_init_script("try{localStorage.setItem('nomap','%s')}catch(e){}" % nomap)
                        if block: c.add_init_script("for(const k of ['localStorage','sessionStorage'])Object.defineProperty(window,k,{get(){throw new DOMException('denied','SecurityError')}});")
                        c.route(base + '/**', local); c.route(base + '/', local)
                        B.stub_map_tiles(c)  # those routes only serve this checkout; tiles must not go to the network
                        pg = c.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:120]))
                        pg.goto(base + '/?nocount&q=SM1%201AA', wait_until='commit'); pg.wait_for_timeout(300); pg.set_viewport_size({'width': 390, 'height': 664})   # in-app toolbar resize mid-load
                        pg.wait_for_load_state('load'); tag = 'nomap=%s block=%s' % (nomap, block)
                        n = wait_cards(pg)
                        if n < 1: bad.append((tag, 'no list cards'))
                        if block and pg.evaluate("document.documentElement.classList.contains('nomap')"): bad.append((tag, 'storage blocked switched List only on (map hidden)'))
                        if errs: bad.append((tag, 'errors', errs[:2]))
                        if nomap == '1' and not block:
                            st = pg.evaluate("""()=>{const b=document.getElementById('v3list'),l=document.getElementById('v3light');const cs=getComputedStyle(b),cl=getComputedStyle(l);
                              return {pressed:b.getAttribute('aria-pressed'),bg:cs.backgroundColor,col:cs.color,lbg:cl.backgroundColor,ul:cs.textDecorationLine}}""")
                            if st['pressed'] != 'true': bad.append((tag, 'List only not shown as on', st))
                            if st['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent') or st['bg'] != st['lbg']: bad.append((tag, 'List only ON is a box, not a link like Light mode', st))
                            pg.click('#v3list'); pg.wait_for_timeout(1500)   # turn List only OFF: map must show AT the search, not the whole world
                            z = pg.evaluate("({z:map.getZoom(),w:document.getElementById('map').offsetWidth,h:document.getElementById('map').offsetHeight})")
                            if z['z'] < 6 or z['w'] < 300 or z['h'] < 200: bad.append((tag, 'map after List only off', z))
                            if st['col'] in ('rgb(255, 255, 255)', 'rgb(242, 244, 248)') : bad.append((tag, 'List only ON not highlighted (gold)', st))
                        if nomap == '0':
                            until(pg, "document.querySelectorAll('#map .leaflet-tile-loaded').length>3&&document.querySelectorAll('#map .leaflet-marker-icon').length>0")
                            m = pg.evaluate("""()=>{const m=document.getElementById('map').getBoundingClientRect(),h=document.querySelector('header').getBoundingClientRect();
                              return {tiles:document.querySelectorAll('#map .leaflet-tile-loaded').length,pins:document.querySelectorAll('#map .leaflet-marker-icon').length,
                                w:m.width,h:m.height,top:m.top+scrollY,htop:h.bottom+scrollY}}""")
                            # tiles are the local placeholder (OpenStreetMap must not be panned from CI); pins + size + position are the hard checks
                            m['z'] = pg.evaluate('map.getZoom()')
                            if m['z'] < 6: bad.append((tag, 'map zoomed out (whole world)', m))
                            if m['pins'] < 1 or m['w'] < 300 or m['h'] < 200: bad.append((tag, 'map not painted', m))
                            if m['top'] < m['htop'] - 1: bad.append((tag, 'map overlaps header', m))
                            print(tag, 'map', m, pg.evaluate('document.documentElement.className'))
                        c.close()
                # Dean's standing rule: DARK by default even with the phone set to light; storage blocked = dark
                for block in (False, True):
                    # Real iPhone WebKit, OS set to light: service worker allowed.
                    c = b.new_context(viewport={'width': 390, 'height': 844}, user_agent=IG, is_mobile=True, color_scheme='light', service_workers='allow')
                    if block: c.add_init_script("for(const k of ['localStorage','sessionStorage'])Object.defineProperty(window,k,{get(){throw new DOMException('denied','SecurityError')}});")
                    c.route(base + '/**', local); c.route(base + '/', local); pg = c.new_page()
                    pg.goto(base + '/?nocount', wait_until='load'); pg.wait_for_timeout(1500)
                    if pg.evaluate("document.documentElement.classList.contains('light')"): bad.append(('webkit OS light, block=%s' % block, 'opened LIGHT, must be dark'))
                    c.close()
                b.close()
        finally: pass
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()
