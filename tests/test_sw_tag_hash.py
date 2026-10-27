"""Stale sw.js under a reused tag (27 Oct 2026 outage, after PR 193).

Cloudflare stored the old fyfb-v90 worker under sw.js?v=57 because that URL was fetched on live before the deploy, so
Safari kept the old worker and the grey map. The tag is now a hash of sw.js (its ?v= precache entries left out, so the
refresh workflows' SHELL sync can't make it drift), and index.html clears fyfb-v90 / fyfb-tiles leftovers once.
"""
import hashlib, os, re, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()
USED_TAGS = {'57'} | {str(n) for n in range(1, 57)}  # every numeric tag ever used, including the poisoned v=57


def sw_tag():
    return 'h' + hashlib.sha256(re.sub(r"\?v=[\w.-]+", '', rd('sw.js')).encode()).hexdigest()[:12]



# Backup style with a drawn feature: grey background plus a green UK fill. A grey-only canvas fails the pixel check.
OFM_DRAWN = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"uk","type":"fill","source":"uk","paint":{"fill-color":"#1e9e3c"}}]}')


def canvas_fill_share(pg):
    """Share of the MapLibre canvas's on-screen pixels showing the green fill (screenshot, so WebGL buffers don't matter)."""
    import base64
    el = pg.locator('#map canvas.maplibregl-canvas, #map .maplibregl-canvas').first
    b64 = base64.b64encode(el.screenshot()).decode()
    return pg.evaluate("""b64 => new Promise((ok, bad) => { const im = new Image(); im.onload = () => {
        const cv = document.createElement('canvas'); cv.width = im.width; cv.height = im.height;
        const x = cv.getContext('2d'); x.drawImage(im, 0, 0); const d = x.getImageData(0, 0, cv.width, cv.height).data;
        let g = 0, n = 0; for (let i = 0; i < d.length; i += 16) { n++; if (d[i+1] > d[i] + 60 && d[i+1] > d[i+2] + 60) g++; }
        ok(n ? g / n : 0) }; im.onerror = bad; im.src = 'data:image/png;base64,' + b64; })""", b64)

class Tag(unittest.TestCase):
    def test_registration_uses_the_content_hash(self):
        m = re.search(r"register\('sw\.js\?v=([\w.-]+)'", rd('layers.js'))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), sw_tag(), 'sw.js changed: set layers.js register tag to sha256 of sw.js (no ?v= parts)')
        self.assertNotIn(m.group(1), USED_TAGS)
        self.assertIn("updateViaCache:'none'", rd('layers.js'))

    def test_layers_js_tag_matches_its_content(self):
        lh = 'h' + hashlib.sha256(open(os.path.join(R, 'layers.js'), 'rb').read()).hexdigest()[:12]
        self.assertIn('layers.js?v=' + lh, rd('index.html'))
        self.assertIn('layers.js?v=' + lh, rd('sw.js'))

    def test_old_cache_self_heal_is_in_the_head(self):
        h = rd('index.html'); i = h.index("k='hmHealOld'")
        self.assertLess(i, h.index('</head>'))
        for s in ("'fyfb-v90'", "'fyfb-tiles'", 'caches.delete', 'unregister()', 'location.reload()', 'sessionStorage.setItem(k'):
            self.assertIn(s, h[i:i + 900])


from test_iphone_map_fix import HAVE, IPhone, BASE, png, old_sw, until, PAINTED, STATE, OFM
SHOTS = os.environ.get('HELPMAP_SHOTS', '/tmp/helpmap_sw_shots')


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class StaleWorker(unittest.TestCase):
    _ctx = IPhone._ctx
    def test_poisoned_old_worker_heals_once_and_map_paints(self):
        """The old v90 worker is still served (as Cloudflare did); the page clears its caches and reloads exactly once."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, c, holder = self._ctx(p, sw_body=old_sw('e3982436c'))
            c.route('**://tile.openstreetmap.org/**', png)
            loads = []
            pg = c.new_page(); pg.on('load', lambda *_: loads.append(1))
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, "async () => (await caches.keys()).includes('fyfb-v90')", 30), 'old worker made no fyfb-v90 cache')
            holder['sw'] = None  # the deploy: this checkout's sw.js under its new hash tag
            n = len(loads)
            pg.reload(wait_until='load')
            self.assertTrue(until(pg, "() => sessionStorage.getItem('hmHealOld')==='1'", 20), 'self-heal did not run')
            self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return !k.includes('fyfb-v90') && !k.includes('fyfb-tiles') }", 30),
                            pg.evaluate('async () => await caches.keys()'))
            self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
            pg.wait_for_timeout(2000)
            self.assertLessEqual(len(loads) - n, 3, 'reload loop')
            self.assertEqual(pg.evaluate(STATE)['active'], 'osm')
            b.close()

    def _healed(self, p):
        """(1) Old v90 worker + fyfb-v90/fyfb-tiles caches installed, then the new build: heals exactly once, ends on the
        new caches, OSM draws. Returns the live page for the offline / backup follow-ups."""
        b, c, holder = self._ctx(p, sw_body=old_sw('e3982436c'))
        net = {'off': False, 'osm': 0}
        def osm(route):
            if net['off']:
                return route.abort('internetdisconnected')
            net['osm'] += 1; png(route)
        c.route('**://tile.openstreetmap.org/**', osm)
        pg = c.new_page(); navs = []
        pg.on('framenavigated', lambda f: f == pg.main_frame and navs.append(f.url))
        pg.goto(BASE + '/?nocount', wait_until='load')
        self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return k.includes('fyfb-v90') && k.includes('fyfb-tiles') }", 30),
                        pg.evaluate('async () => await caches.keys()'))
        holder['sw'] = None
        before = len(navs)
        pg.goto(BASE + '/?nocount', wait_until='load')
        self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return k.includes('fyfb-v92') && k.includes('fyfb-tiles2') && !k.includes('fyfb-v90') && !k.includes('fyfb-tiles') }", 40),
                        pg.evaluate('async () => await caches.keys()'))
        self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
        pg.wait_for_timeout(3000)
        self.assertEqual(len(navs) - before, 2, ('expected the visit plus exactly one heal reload', navs[before:]))
        self.assertEqual(pg.evaluate("() => sessionStorage.getItem('hmHealOld')"), '1')
        self.assertTrue(pg.evaluate("() => !!navigator.serviceWorker.controller && /sw\\.js\\?v=h[0-9a-f]{12}$/.test(navigator.serviceWorker.controller.scriptURL)"),
                        pg.evaluate("() => navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL"))
        return b, c, pg, net, navs

    def test_heal_once_webkit(self):
        """(1) on WebKit iPhone 13. Offline after the heal is checked in Chromium below: Playwright's request routing
        in WebKit keeps tile responses out of the worker's cache (the cache stays empty even with the live code), so
        an offline check here would test the harness, not the site."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, *_ = self._healed(p); b.close()

    def test_heal_then_osm_blocked_in_worker_switches_to_openfreemap(self):
        """(3): worker ON, OSM refused for page and worker fetches; the backup draws and the page keeps responding."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            blocker = "const __f=self.fetch;self.fetch=function(r,o){var u=typeof r==='string'?r:r.url;return /tile\\.openstreetmap\\.org/.test(u)?Promise.reject(new TypeError('blocked by test')):__f.call(self,r,o)};\n"
            b, c, holder = self._ctx(p, sw_body=(blocker + open(os.path.join(R, 'sw.js'), encoding='utf-8').read()).encode())
            c.route('**://tile.openstreetmap.org/**', lambda r: r.abort('connectionrefused'))
            c.route('**://*.openfreemap.org/**', lambda r: r.fulfill(status=200, content_type='application/json', body=OFM_DRAWN,
                                                                         headers={'access-control-allow-origin': '*'}) if '/styles/' in r.request.url
                    else r.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'}))
            pg = c.new_page()
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
            self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller", 20), 'worker not on')
            pg.reload(wait_until='load')
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='openfreemap' && !!document.querySelector('#map canvas.maplibregl-canvas, #map .maplibregl-canvas')", 40),
                            pg.evaluate(STATE))
            fo = pg.evaluate('() => window.TILE_FAILOVER')
            self.assertEqual((fo['from'], fo['to']), ('osm', 'openfreemap'))
            gaps = pg.evaluate("""() => new Promise(done => { let last = performance.now(), worst = 0, n = 0;
              const t = setInterval(() => { const now = performance.now(); worst = Math.max(worst, now - last); last = now;
                if (++n === 30) { clearInterval(t); done(worst) } }, 100); })""")
            self.assertLess(gaps, 1000, 'main thread froze %dms' % gaps)
            pg.evaluate("() => map.setView([53.48, -2.24], 7)"); pg.wait_for_timeout(800)
            self.assertEqual(pg.evaluate('() => window.TILE_ACTIVE'), 'openfreemap')
            # A canvas existing is not enough: a grey map would pass. The style fills the UK green, so the backup
            # canvas must actually show that colour (not blank, not the grey background).
            share = 0
            for _ in range(20):
                pg.wait_for_timeout(500)
                share = canvas_fill_share(pg)
                if share >= 0.2: break
            self.assertGreaterEqual(share, 0.2, ('backup map canvas not drawn (grey/blank): green share %.3f' % share, pg.evaluate(STATE)))
            os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, 'sw_on_osm_blocked_backup.png'))
            b.close()

    def test_clean_phone_never_reloads(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, c, _ = self._ctx(p)
            c.route('**://tile.openstreetmap.org/**', png)
            loads = []
            pg = c.new_page(); pg.on('load', lambda *_: loads.append(1))
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
            pg.wait_for_timeout(12000)  # a clean phone must never reload: exactly one page load over ~12 s
            self.assertEqual(len(loads), 1, 'clean phone reloaded: %d page loads in ~12s' % len(loads))
            self.assertIsNone(pg.evaluate("() => sessionStorage.getItem('hmHealOld')"))
            b.close()


del IPhone  # run its tests once, in test_iphone_map_fix
if __name__ == '__main__': unittest.main()


class OfflineAfterHeal(unittest.TestCase):
    """(2) Old v90 worker + caches, then the new build heals once; then offline the page and cached OSM tiles still
    load. Chromium with real local servers (host-rules), the same harness as test_osm_default's offline check."""
    @unittest.skipUnless(__import__('test_osm_default').HAVE, 'needs playwright chromium')
    def test_heal_then_offline(self):
        import http.server, ssl, subprocess, tempfile, threading
        from urllib.parse import urlparse
        from playwright.sync_api import sync_playwright
        import test_osm_default as O
        body = {'sw': subprocess.check_output(['git', 'show', 'e3982436c:sw.js'], cwd=R)}
        off = {'on': False}; offline_hits = []

        class Site(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k): super().__init__(*a, directory=R, **k)
            def log_message(self, *a): pass
            def do_GET(self):
                if urlparse(self.path).path == '/sw.js':
                    d = body['sw'] if body['sw'] is not None else open(os.path.join(R, 'sw.js'), 'rb').read()
                    self.send_response(200); self.send_header('Content-Type', 'application/javascript')
                    self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(d))); self.end_headers()
                    self.wfile.write(d); return
                super().do_GET()

        class Tiles(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                if off['on']: offline_hits.append(self.path)
                self.send_response(200); self.send_header('Content-Type', 'image/png'); self.send_header('Content-Length', str(len(O.BLANK)))
                self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers(); self.wfile.write(O.BLANK)

        certs = tempfile.mkdtemp()
        subprocess.check_call(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', certs + '/k.pem', '-out', certs + '/c.pem',
                               '-days', '1', '-nodes', '-subj', '/CN=tile.openstreetmap.org'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sc = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); sc.load_cert_chain(certs + '/c.pem', certs + '/k.pem')
        tiles = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Tiles); tiles.socket = sc.wrap_socket(tiles.socket, server_side=True)
        site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Site)
        for srv in (tiles, site): threading.Thread(target=srv.serve_forever, daemon=True).start()
        rules = ', '.join('MAP %s 127.0.0.1:%d' % (h, tiles.server_address[1]) for h in O.STUB_HOSTS)
        url = 'http://127.0.0.1:%d/?nocount' % site.server_address[1]
        PAINT = """() => [...document.querySelectorAll('#map .leaflet-tile-loaded')].filter(i => i.src.includes('tile.openstreetmap.org') && i.naturalWidth > 0).length >= 4"""
        try:
            with sync_playwright() as p:
                br = p.chromium.launch(args=['--host-rules=' + rules, '--ignore-certificate-errors'])
                ctx = br.new_context(viewport={'width': 390, 'height': 844}, service_workers='allow', user_agent='Mozilla/5.0 helpmap-check')
                pg = ctx.new_page(); navs = []
                pg.on('framenavigated', lambda f: f == pg.main_frame and navs.append(f.url))
                pg.goto(url, wait_until='domcontentloaded')
                self.assertTrue(O.until(pg, "async () => (await caches.keys()).includes('fyfb-v90')", 30), 'old worker not installed')
                body['sw'] = None; n = len(navs)
                pg.goto(url, wait_until='domcontentloaded')
                self.assertTrue(O.until(pg, "async () => { const k = await caches.keys(); return k.includes('fyfb-v92') && !k.includes('fyfb-v90') && !k.includes('fyfb-tiles') }", 30))
                self.assertTrue(O.until(pg, PAINT, 30), 'no map after heal')
                pg.wait_for_timeout(2500)
                self.assertEqual(len(navs) - n, 2, navs[n:])  # the visit + exactly one heal reload
                pg.reload(wait_until='domcontentloaded'); self.assertTrue(O.until(pg, PAINT, 30))
                self.assertTrue(O.until(pg, "async () => (await (await caches.open('fyfb-tiles2')).keys()).some(r => r.url.includes('tile.openstreetmap.org'))", 10))
                off['on'] = True; ctx.set_offline(True); n = len(navs)
                pg.reload(wait_until='domcontentloaded')
                self.assertTrue(O.until(pg, PAINT, 30), 'offline after heal: cached OSM tiles not shown')
                pg.wait_for_timeout(1500)
                self.assertEqual(len(navs) - n, 1, 'offline visit reloaded again')
                self.assertEqual(offline_hits, [])
                br.close()
        finally:
            site.shutdown(); tiles.shutdown()
