"""Map tile fallback.

The old tiles.js switched only when 6 or more tile errors had arrived and errors also outweighed
successes (bad * 3 > ok). A service-worker or browser cache made most tiles succeed, and the few
uncached ones were HTTP 403 with a PNG body, so that rule never tripped. The trigger now leaves
the provider on any 401, 403 or 429, or on 4 failures inside the last 20 attempts, including after
the first load. OpenStreetMap stays first and OpenFreeMap (vector, MapLibre) is the automatic backup
(Dean, 26 Oct 17:07). Stadia is gone. MapTiler is a disabled future fallback with no key.
Rule 23: every tile, style and vector request is stubbed. No real tile is loaded.

Checks also stub tile hosts. A page opened with check_browser.new_context must not receive a real
tile-host response.
"""
import functools, http.server, importlib.util, json, os, re, sys, threading, unittest, urllib.error
from io import BytesIO

R = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))
import check_browser as B

CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
SHOTS = os.environ.get('HELPMAP_SHOTS') or os.path.join(__import__('tempfile').gettempdir(), 'helpmap-shots')
TILES = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()


def old_rule(ok, bad):
    """The trigger that was in tiles.js: 6 errors, and errors outweigh successes."""
    return bad >= 6 and bad * 3 > ok


def providers():
    import json, subprocess
    js = TILES + "\nprocess.stdout.write(JSON.stringify({all: window.TILE_PROVIDERS, cand: window.tileCandidates().map(p => p.name)}))"
    out = subprocess.run(['node', '-e', 'var window = {};' + js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


# Stub OpenFreeMap style (rule 23: no real vector tiles). A light background plus a filled shape over Britain,
# so the render check can see MapLibre actually drew something.
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
BASE = os.environ.get('HELPMAP_FALLBACK_BASE')  # set to https://helpmap.uk for the live check
OFM_CREDIT = 'OpenFreeMap © OpenMapTiles Data from OpenStreetMap'


class Config(unittest.TestCase):
    def test_chain_is_osm_then_openfreemap_and_maptiler_disabled(self):
        d = providers()
        self.assertEqual(d['cand'], ['osm', 'openfreemap'])
        names = [p['name'] for p in d['all']]
        self.assertEqual(names, ['osm', 'openfreemap', 'maptiler'])
        ofm = d['all'][1]
        self.assertEqual(ofm['type'], 'vector')
        self.assertEqual(ofm['url'], 'https://tiles.openfreemap.org/styles/positron')
        self.assertNotIn('dark', ofm['url'])
        plain = re.sub(r'<[^>]+>', '', ofm['attribution']).replace('&copy;', '©')
        self.assertEqual(re.sub(r'\s+', ' ', plain).strip(), OFM_CREDIT)
        mt = d['all'][2]
        self.assertTrue(mt['disabled'])
        self.assertEqual(mt['key'], '')
        self.assertNotIn('stadia', TILES.lower().replace('stadia is not used', ''))
        self.assertIn('permanent default', TILES)
        self.assertNotIn('2026-11-22', TILES)
        self.assertIsNone(re.search(r'\bDate\b', TILES))
        for rel in ('README.md', 'privacy.html', 'terms.html', 'faq.html', 'scripts/seo_meta.py', 'index.html'):
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            self.assertNotIn('Map © MapTiler © OpenStreetMap', text, rel)
            self.assertNotIn('2026-11-22', text, rel)
            self.assertNotIn('tiles.stadiamaps.com', text, rel)
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        csp = re.search(r'Content-Security-Policy" content="([^"]+)"', home).group(1)
        for d_ in ('img-src', 'connect-src'):
            part = re.search(d_ + r' ([^;]+);', csp).group(1)
            self.assertIn('https://tiles.openfreemap.org', part, d_)
        self.assertIn("worker-src 'self'", csp)
        for f in ('maplibre-gl-csp.js', 'maplibre-gl-csp-worker.js', 'maplibre-gl.css', 'leaflet-maplibre-gl.js'):
            self.assertTrue(os.path.exists(os.path.join(R, 'vendor', f)), f)
            self.assertIn('vendor/' + f, TILES)

    def test_a_key_does_not_enable_maptiler(self):
        import json, subprocess
        js = TILES + "\nwindow.TILE_PROVIDERS[2].key='abc';window.TILE_PROVIDERS.reverse();process.stdout.write(JSON.stringify(window.tileCandidates().map(p=>p.name)))"
        out = json.loads(subprocess.run(['node', '-e', 'var window = {};' + js], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out, ['osm', 'openfreemap'])

    def test_no_real_tiles_in_ci(self):
        wf = os.path.join(R, '.github', 'workflows')
        self.assertFalse(os.path.exists(os.path.join(wf, 'tile-monitor.yml')))
        self.assertFalse(os.path.exists(os.path.join(R, 'scripts', 'tile_monitor.py')))
        for name in os.listdir(wf):
            text = open(os.path.join(wf, name), encoding='utf-8').read()
            self.assertNotIn('HELPMAP_REAL_TILES', text, name)
        lock = open(os.path.join(R, 'scripts', 'design_lock.py'), encoding='utf-8').read()
        self.assertNotIn('one_real_tile', lock)
        self.assertNotIn('one_real_tile', open(os.path.join(R, 'scripts', 'check_browser.py'), encoding='utf-8').read())

    def test_footer_credit_matches_the_welsh_rule(self):
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        footer = re.search(r'<footer>.*?</footer>', home, re.S).group(0)
        node = [p for p in re.split(r'<[^>]+>', footer) if 'OpenStreetMap contributors' in p and 'Built by' in p][0]
        self.assertEqual(node, '). Map © OpenStreetMap contributors. Backup map: OpenFreeMap © OpenMapTiles. © MapTiler. Built by ')
        layers = open(os.path.join(R, 'layers.js'), encoding='utf-8').read()
        self.assertIn(r'/^\)\. Map © OpenStreetMap contributors\. Backup map: OpenFreeMap © OpenMapTiles\. © MapTiler\. Built by $/', layers)

    def test_old_mix_of_cached_successes_and_a_few_403s_did_not_switch(self):
        # What a mostly-cached view looked like: many 200s, fewer than 6 errors.
        self.assertFalse(old_rule(20, 5))
        self.assertFalse(old_rule(8, 2))
        # Six errors still lost when successes outnumbered them (bad * 3 > ok is 18 > 20).
        self.assertFalse(old_rule(20, 6))
        self.assertTrue(old_rule(10, 6))

    def test_stub_is_wired_and_real_tiles_env_skips_it(self):
        live = open(os.path.join(R, 'scripts', 'check_browser.py'), encoding='utf-8').read()
        self.assertIn('def stub_map_tiles', live)
        self.assertIn('HELPMAP_REAL_TILES', live)
        self.assertIn('stub_map_tiles(c)', live)
        ready = open(os.path.join(R, 'tests', 'site_ready.py'), encoding='utf-8').read()
        self.assertIn('stub_map_tiles(page)', ready)
        for rel in ('scripts/old_links.py', 'scripts/newlook_parity.py', 'tests/test_updated_dates.py', 'tests/test_webkit_instagram.py', 'tests/newlook_render.py', 'tests/test_saved_type_q.py'):
            self.assertIn('stub_map_tiles', open(os.path.join(R, rel), encoding='utf-8').read(), rel)
        old = open(os.path.join(R, 'scripts', 'old_links.py'), encoding='utf-8').read()
        route_at = old.find("c.route('**/*', serve_old)")
        unroute_at = old.find("c.unroute('**/*', serve_old)")
        self.assertGreater(route_at, 0)
        self.assertIn('stub_map_tiles(c)', old[route_at:route_at + 220])
        self.assertIn('stub_map_tiles(c)', old[unroute_at:unroute_at + 220])
        dark = open(os.path.join(R, 'scripts', 'dark_default.py'), encoding='utf-8').read()
        body = dark.split('"""', 2)[-1]
        self.assertIn('B.new_context(', body)
        self.assertNotIn('b.new_context(', body)
        called = []

        class Target:
            def route(self, pattern, handler):
                called.append(pattern)

        self.assertTrue(B.stub_map_tiles(Target()))
        os.environ['HELPMAP_REAL_TILES'] = '1'
        try:
            self.assertFalse(B.stub_map_tiles(Target()))
        finally:
            del os.environ['HELPMAP_REAL_TILES']
        self.assertEqual(len(called), 1)
        self.assertTrue(B.TILE_PNG.startswith(b'\x89PNG'))

    def test_one_fetch_paints_the_tile_and_locate_does_not_fly_the_zoom_ladder(self):
        """The 3-in-20 refusal rule stays. A tile is one fetch (status + body). Locate does not animate
        through the zooms in between, and a zoom animation does not request a grid at each level."""
        self.assertIn('window.TILE_WINDOW = 20', TILES)
        self.assertIn('window.TILE_WINDOW_REFUSALS = 3', TILES)
        self.assertIn('btoa(parts.join', TILES)
        self.assertNotIn('readAsDataURL', TILES)
        self.assertNotIn('createObjectURL', TILES)
        self.assertIn("referrerPolicy: 'strict-origin-when-cross-origin'", TILES)
        self.assertIn('updateWhenZooming: false', TILES)
        self.assertIn('keepBuffer: 2', TILES)
        self.assertIn('data-tile', TILES)
        self.assertNotIn('updateWhenZooming: true', TILES)
        with open(os.path.join(R, 'index.html'), encoding='utf-8') as fh:
            home = fh.read()
        self.assertIn('fitBounds(window._fitB,{animate:false})', home)


def _server():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE:
            return
        cls.srv = _server()
        cls.base = BASE.rstrip('/') + '/?nocount' if BASE else 'http://127.0.0.1:%d/?nocount' % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        if HAVE:
            cls.srv.shutdown()

    def setUp(self):
        if not HAVE:
            self.skipTest('needs chrome + playwright')

    def _chrome(self, p):
        return p.chromium.launch(executable_path=CH, args=['--enable-unsafe-swiftshader', '--use-angle=swiftshader'])

    def _ofm_ready(self, pg, mix):
        self.assertTrue(_until(pg, "() => window.TILE_VECTOR==='ready' && !!document.querySelector('#map .leaflet-gl-layer canvas')", secs=20),
                        pg.evaluate("() => ({active: window.TILE_ACTIVE, v: window.TILE_VECTOR || null})"))
        self.assertTrue(any('/styles/positron' in u for u in mix.get('ofm', [])), mix.get('ofm'))
        credit = pg.evaluate("() => (document.querySelector('.leaflet-control-attribution')||{}).innerText||''")
        self.assertIn(OFM_CREDIT, re.sub(r'\\s+', ' ', credit))
        filt = pg.evaluate("() => getComputedStyle(document.querySelector('#map .leaflet-gl-layer')).filter")
        self.assertEqual(filt, 'none')

    def test_new_context_makes_no_real_tile_requests(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(SHOTS, exist_ok=True)
        with sync_playwright() as p:
            b = self._chrome(p)
            c = B.new_context(b, viewport={'width': 1100, 'height': 800}, color_scheme='dark', service_workers='block')
            pg = c.new_page()
            failed, tiles = [], []

            def on_fail(req):
                if B.TILE_RE.search(req.url):
                    failed.append(req.url)

            def on_resp(resp):
                if B.TILE_RE.search(resp.url):
                    tiles.append(resp)

            pg.on('requestfailed', on_fail)
            pg.on('response', on_resp)
            B.goto(pg, self.base)
            pg.wait_for_timeout(1200)
            self.assertTrue(tiles, 'the map asked for no tiles, so the stub was not exercised')
            self.assertEqual(failed, [])
            hosts = set()
            for resp in tiles:
                hosts.add(resp.url.split('/')[2])
                self.assertEqual(resp.status, 200, resp.url)
                self.assertEqual((resp.header_value('x-helpmap-tile') or '').lower(), 'stub', resp.url)
                body = resp.body()
                if body:
                    self.assertEqual(body, B.TILE_PNG, resp.url)
            self.assertEqual(hosts, {'tile.openstreetmap.org'})
            state = pg.evaluate("""()=>({
              active: window.TILE_ACTIVE,
              order: window.TILE_ORDER,
              credit: (document.querySelector('.leaflet-control-attribution')||{}).innerText||'',
              filter: getComputedStyle(document.querySelector('#map .leaflet-tile-pane')).filter
            })""")
            self.assertEqual(state['active'], 'osm')
            self.assertEqual(state['order'][0], 'osm')
            self.assertNotIn('maptiler', state['order'])
            self.assertIn('OpenStreetMap', state['credit'])
            self.assertNotIn('MapTiler', state['credit'])
            self.assertNotIn('Stadia', state['credit'])
            self.assertEqual(state['filter'], 'none')
            pinned = pg.evaluate("""()=>{
              var list = window.TILE_PROVIDERS.map(function(p){return Object.assign({}, p)});
              var mt = list.filter(function(p){return p.name==='maptiler'})[0];
              mt.key = 'abc';
              window.TILE_PROVIDERS = [mt].concat(list.filter(function(p){return p.name!=='maptiler'}));
              var names = window.tileCandidates().map(function(p){return p.name});
              return names;
            }""")
            self.assertEqual(pinned[0], 'osm')
            self.assertNotIn('maptiler', pinned)
            self.assertNotIn('stadia', state['order'])
            self.assertEqual(state['order'], ['osm', 'openfreemap'])
            pg.click('#v3light')
            pg.wait_for_timeout(300)
            light = pg.evaluate("""()=>({
              on: document.documentElement.classList.contains('light'),
              filter: getComputedStyle(document.querySelector('#map .leaflet-tile-pane')).filter
            })""")
            self.assertTrue(light['on'])
            self.assertEqual(light['filter'], 'none')
            pg.fill('#q', 'Cornwall')
            pg.press('#q', 'Enter')
            self.assertTrue(_until(pg, "() => document.querySelectorAll('#list .card').length>0"))
            pg.screenshot(path=os.path.join(SHOTS, 'map-osm-default.png'))
            b.close()

    def test_osm_blocked_switches_to_openfreemap_and_renders(self):
        """Dean 26 Oct 17:12: OSM tile requests are aborted, the map switches to OpenFreeMap on its own,
        and the OpenFreeMap map visibly renders (non-blank pixels) with OpenFreeMap's credit shown."""
        from playwright.sync_api import sync_playwright
        os.makedirs(SHOTS, exist_ok=True)
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block', color_scheme='dark', user_agent=B.user_agent(1100))  # helpmap-check: Cloudflare skip rule
            pg = c.new_page()
            seen = {'osm_aborted': 0, 'ofm': [], 'other_tile': []}

            def handle(route):
                url = route.request.url
                if 'tile.openstreetmap.org' in url:
                    seen['osm_aborted'] += 1
                    route.abort('connectionrefused')
                elif 'tiles.openfreemap.org' in url:
                    seen['ofm'].append(url)
                    if '/styles/positron' in url:
                        route.fulfill(status=200, content_type='application/json', body=OFM_STYLE,
                                      headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
                    else:
                        route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
                else:
                    seen['other_tile'].append(url)
                    route.abort()

            pg.route(B.TILE_RE, handle)
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='openfreemap'", secs=20),
                            pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null})"))
            fo = pg.evaluate("() => window.TILE_FAILOVER")
            self.assertEqual((fo['from'], fo['to']), ('osm', 'openfreemap'))
            self.assertGreaterEqual(seen['osm_aborted'], 4)
            self.assertEqual(seen['other_tile'], [])
            self._ofm_ready(pg, {'ofm': seen['ofm']})
            pg.wait_for_timeout(800)
            px = pg.evaluate("""() => new Promise(done => {
              var lyr; map.eachLayer(function (l) { if (l.getMaplibreMap) lyr = l; });
              var gl = lyr.getMaplibreMap(), cv = gl.getCanvas();
              gl.once('render', function () {
                var ctx = cv.getContext('webgl2') || cv.getContext('webgl'), w = cv.width, h = cv.height, n = 0, lit = 0, colours = {};
                var buf = new Uint8Array(4);
                for (var i = 1; i < 10; i++) for (var j = 1; j < 10; j++) {
                  ctx.readPixels(Math.floor(w * i / 10), Math.floor(h * j / 10), 1, 1, ctx.RGBA, ctx.UNSIGNED_BYTE, buf);
                  n++; if (buf[3] > 0) lit++; colours[buf.join(',')] = 1;
                }
                done({n: n, lit: lit, colours: Object.keys(colours)});
              });
              gl.triggerRepaint();
            })""")
            self.assertEqual(px['lit'], px['n'], px)  # every sampled pixel painted: not blank
            self.assertTrue(any(c.startswith('168,208,141') for c in px['colours']), px)  # the stub land fill drew
            pg.locator('#map').screenshot(path=os.path.join(SHOTS, 'map-openfreemap-fallback-osm-blocked.png'))
            b.close()

    def _mix(self, page, fail_after, bad_limit, switch_on, code=403):
        """OSM: the first fail_after requests are 200, then up to bad_limit distinct URLs are 403
        with a real PNG body (and every repeat of those URLs, including the status probe). The rest
        stay 200. OpenFreeMap gets a stub light style (no real vector tiles); other hosts are 404.
        switch_on['on'] forces every new OSM tile to 403, at most switch_on['max'] distinct URLs if set.
        code is the refusal status (403 by default, 429 to model rate limiting)."""
        state = {'ok': 0, 'bad': set(), 'n403': 0, 'n200': 0}

        def handle(route):
            url = route.request.url.split('?')[0]
            if 'tiles.openfreemap.org' in url:
                state.setdefault('ofm', []).append(url)
                if '/styles/positron' in url:
                    route.fulfill(status=200, content_type='application/json', body=OFM_STYLE,
                                  headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
                else:
                    route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
                return
            if 'tile.openstreetmap.org' not in url:
                route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
                return
            status = 200
            if 'tile.openstreetmap.org' in url:
                if url in state['bad']:
                    status = 403
                elif switch_on['on'] and len(state['bad']) < switch_on.get('max', 10**9):
                    status = 403
                    state['bad'].add(url)
                elif url in state.setdefault('seen', set()):
                    pass  # repeat of a 200 (the image after the status fetch) stays 200
                else:
                    state['seen'].add(url)
                    state['ok'] += 1
                    if state['ok'] > fail_after and len(state['bad']) < bad_limit:
                        status = 403
                        state['bad'].add(url)
                        state['ok'] -= 1
            if status == 403:
                status = code
                state['n403'] += 1
            else:
                state['n200'] += 1
            route.fulfill(status=status, content_type='image/png', body=B.TILE_PNG, headers={
                'access-control-allow-origin': '*',
                'cache-control': 'public, max-age=86400',
            })

        page.route(B.TILE_RE, handle)
        return state

    def test_partial_403_amongst_200s_switches_before_the_old_rule(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(SHOTS, exist_ok=True)
        with sync_playwright() as p:
            b = self._chrome(p)
            # One or two refusals amongst 200s must not switch.
            for limit in (1, 2):
                c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
                pg = c.new_page()
                mix = self._mix(pg, fail_after=8, bad_limit=limit, switch_on={'on': False})
                from site_ready import open_map
                open_map(pg, self.base, stub_tiles=False)
                self.assertTrue(_until(pg, "() => window.TILE_STATS && window.TILE_STATS.error >= %d" % limit, secs=8),
                                pg.evaluate("() => ({active: window.TILE_ACTIVE, stats: window.TILE_STATS})"))
                pg.wait_for_timeout(1500)
                self.assertEqual(len(mix['bad']), limit)
                self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm', limit)
                self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"), limit)
                c.close()
            # Three switch.
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            seen = {'200': 0, '403': 0, 'png403': 0, 'maptiler': 0}
            pg.on('response', lambda r: _note(seen, r))
            pg.on('request', lambda r: seen.__setitem__('maptiler', seen['maptiler'] + (1 if 'maptiler.com' in r.url else 0)))
            mix = self._mix(pg, fail_after=8, bad_limit=3, switch_on={'on': False})
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => !!(window.TILE_FAILOVER && window.TILE_ACTIVE==='openfreemap')", secs=8),
                            {'page': pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER, stats: window.TILE_STATS})"),
                             'mix': {k: (list(v) if isinstance(v, set) else v) for k, v in mix.items()},
                             'seen': dict(seen)})
            self._ofm_ready(pg, mix)
            fo = pg.evaluate("() => window.TILE_FAILOVER")
            self.assertEqual(fo['from'], 'osm')
            self.assertEqual(fo['to'], 'openfreemap')
            self.assertGreaterEqual(fo['ok'], 1)
            self.assertEqual(fo['bad'], 3, fo)
            self.assertEqual(fo['refused'], 3, fo)
            self.assertFalse(old_rule(fo['ok'], fo['bad']), fo)
            self.assertEqual(str(fo['reason']), '403')
            self.assertGreaterEqual(seen['200'], 1)
            self.assertGreaterEqual(seen['403'], 3)
            self.assertGreaterEqual(seen['png403'], 3)
            self.assertEqual(seen['maptiler'], 0)
            pg.screenshot(path=os.path.join(SHOTS, 'map-openfreemap-fallback.png'))
            b.close()

    def test_a_single_429_does_not_switch(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            seen = {'429': 0}
            pg.on('response', lambda r: seen.__setitem__('429', seen['429'] + (1 if 'tile.openstreetmap.org' in r.url and r.status == 429 else 0)))
            mix = self._mix(pg, fail_after=8, bad_limit=1, switch_on={'on': False}, code=429)
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => window.TILE_STATS && window.TILE_STATS.error >= 1", secs=8))
            pg.wait_for_timeout(1500)
            self.assertEqual(seen['429'], 1)
            self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm')
            self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"))
            self.assertTrue(_until(pg, "() => document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
            b.close()

    def test_one_404_does_not_switch(self):
        """A missing tile is one error, not a refusal. One 404 must not leave OpenStreetMap."""
        from collections import Counter
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            urls = []
            pg.on('request', lambda r: urls.append(r.url.split('?')[0]) if 'tile.openstreetmap.org' in r.url else None)
            seen = {'404': 0}
            pg.on('response', lambda r: seen.__setitem__('404', seen['404'] + (1 if 'tile.openstreetmap.org' in r.url and r.status == 404 else 0)))
            mix = self._mix(pg, fail_after=8, bad_limit=1, switch_on={'on': False}, code=404)
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => window.TILE_STATS && window.TILE_STATS.error >= 1", secs=8),
                            pg.evaluate("() => ({active: window.TILE_ACTIVE, stats: window.TILE_STATS})"))
            pg.wait_for_timeout(1500)
            self.assertEqual(seen['404'], 1)
            self.assertEqual(len(mix['bad']), 1)
            self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm')
            self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"))
            stats = pg.evaluate("() => window.TILE_STATS")
            self.assertGreaterEqual(stats.get('error', 0), 1, stats)
            self.assertGreater(stats.get('load', 0), 3, stats)
            counts = Counter(urls)
            self.assertEqual(max(counts.values()), 1, counts.most_common(3))
            self.assertEqual(counts[next(iter(mix['bad']))], 1)
            self.assertGreater(pg.evaluate("() => document.querySelectorAll('#map .leaflet-tile-loaded').length"), 3)
            b.close()

    def test_one_slow_tile_does_not_switch(self):
        """A tile that answers late is not a failure. The map stays on OpenStreetMap while that
        request is in flight and after the 200 arrives."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            held = {}

            def handle(route):
                url = route.request.url.split('?')[0]
                if 'tile.openstreetmap.org' not in url:
                    return self._osm_ok(route)
                if held.get('arm') and held.get('route') is None and url not in held['fast']:
                    held['route'] = route
                    held['url'] = url
                    return
                held.setdefault('fast', set()).add(url)
                route.fulfill(status=200, content_type='image/png', body=B.TILE_PNG,
                              headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})

            pg.route(B.TILE_RE, handle)
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='osm' && document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
            self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"))
            settled = pg.evaluate("() => window.TILE_STATS.error || 0")
            self.assertEqual(settled, 0)
            held['arm'] = True
            held['fast'] = set()
            pg.evaluate("() => map.panBy([700, 280], {animate: false})")
            for _ in range(40):
                if held.get('route') is not None:
                    break
                pg.wait_for_timeout(100)
            self.assertIsNotNone(held.get('route'), 'pan did not request a new tile')
            pg.wait_for_timeout(2000)
            mid = pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null, stats: window.TILE_STATS})")
            self.assertEqual(mid['active'], 'osm', mid)
            self.assertIsNone(mid['fo'], mid)
            self.assertEqual(mid['stats'].get('error', 0), 0, mid)
            held['route'].fulfill(status=200, content_type='image/png', body=B.TILE_PNG,
                                  headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
            tile = held['url']
            self.assertTrue(_until(pg, """() => [...document.querySelectorAll('#map .leaflet-tile-loaded')]
                .some(img => (img.getAttribute('data-tile')||'') === %s && img.naturalWidth > 0)""" % json.dumps(tile), secs=8),
                            pg.evaluate("() => window.TILE_STATS"))
            done = pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null, stats: window.TILE_STATS})")
            self.assertEqual(done['active'], 'osm', done)
            self.assertIsNone(done['fo'], done)
            self.assertEqual(done['stats'].get('error', 0), 0, done)
            b.close()

    def test_switch_still_happens_after_the_first_load(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            flag = {'on': False}
            # No 403s until flag['on']. bad_limit 0 and fail_after huge means every OSM tile is 200 first.
            state = self._mix(pg, fail_after=10**9, bad_limit=0, switch_on=flag)
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='osm' && document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
            self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"))
            # Two refusals after the first load: still OSM.
            flag['on'] = True
            flag['max'] = 2
            pg.evaluate("() => map.setView([51.5,-0.12], 13)")
            self.assertTrue(_until(pg, "() => window.TILE_STATS.error >= 2"), pg.evaluate("() => window.TILE_STATS"))
            pg.wait_for_timeout(1500)
            self.assertEqual(len(state['bad']), 2)
            self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm')
            self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"))
            # Three refusals inside one 20-tile window switch. (The first two have aged out of the window by now:
            # many successes since, so the rule counts three fresh ones.)
            flag['max'] = 5
            pg.evaluate("() => map.setView([53.48,-2.24], 13)")
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='openfreemap'"), pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER, st: window.TILE_STATS})"))
            fo = pg.evaluate("() => window.TILE_FAILOVER")
            self.assertEqual(fo['from'], 'osm')
            self.assertEqual(fo['to'], 'openfreemap')
            self.assertEqual(fo['refused'], 3, fo)
            self.assertEqual(str(fo['reason']), '403')
            self.assertGreater(state['ok'], 0)
            self._ofm_ready(pg, state)
            b.close()

    def _open(self, p, query, handle):
        b = self._chrome(p)
        c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
        pg = c.new_page()
        pg.route(B.TILE_RE, handle)
        from site_ready import open_map
        sep = '&' if '?' in self.base else '?'
        open_map(pg, self.base + (sep + query if query else ''), stub_tiles=False)
        return b, pg

    @staticmethod
    def _osm_ok(route):
        if 'tile.openstreetmap.org' in route.request.url:
            route.fulfill(status=200, content_type='image/png', body=B.TILE_PNG,
                          headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
        elif '/styles/positron' in route.request.url:
            route.fulfill(status=200, content_type='application/json', body=OFM_STYLE, headers={'access-control-allow-origin': '*'})
        else:
            route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})

    def test_no_debug_readout_without_the_flag(self):
        """Without ?tiles=debug the page is unchanged: no readout element, credit text as before."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, pg = self._open(p, '', self._osm_ok)
            self.assertTrue(_until(pg, "() => document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => document.querySelectorAll('#tiles-debug, .tiles-debug').length"), 0)
            self.assertNotIn('map: ', pg.evaluate("() => document.querySelector('#map').innerText"))
            b.close()

    def test_debug_readout_shows_active_map_and_switch_reason(self):
        """Dean 27 Oct 05:44: iPhone shows the backup map. ?tiles=debug prints why, in plain text."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            def handle(route):
                if 'tile.openstreetmap.org' in route.request.url:
                    route.fulfill(status=403, content_type='image/png', body=B.TILE_PNG, headers={'access-control-allow-origin': '*'})
                else:
                    self._osm_ok(route)
            b, pg = self._open(p, 'tiles=debug', handle)
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='openfreemap'"))
            self.assertTrue(_until(pg, "() => /switched osm->openfreemap/.test((document.getElementById('tiles-debug')||{}).textContent||'')"))
            t = pg.evaluate("() => document.getElementById('tiles-debug').innerText")
            self.assertIn('map: openfreemap', t)
            self.assertIn('reason 403', t)
            self.assertIn('codes 403', t)
            self.assertRegex(t, r'failures \d+')
            b.close()
        with sync_playwright() as p:
            b, pg = self._open(p, 'tiles=debug', self._osm_ok)
            self.assertTrue(_until(pg, "() => /map: osm/.test((document.getElementById('tiles-debug')||{}).textContent||'')"))
            self.assertIn('no switch', pg.evaluate("() => document.getElementById('tiles-debug').innerText"))
            b.close()

    def test_one_failed_fetch_per_tile_is_retried_not_counted(self):
        """Each OSM tile's first request fails at the network level (iOS 'Load failed'), the retry is 200.
        Before the retry this switched to the backup; now OSM stays and nothing counts as a failure."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            seen = set()
            def handle(route):
                u = route.request.url
                if 'tile.openstreetmap.org' in u and u not in seen:
                    seen.add(u)
                    route.abort('connectionreset')
                else:
                    self._osm_ok(route)
            b, pg = self._open(p, '', handle)
            self.assertTrue(_until(pg, "() => document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
            pg.wait_for_timeout(1500)
            st = pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null, stats: window.TILE_STATS})")
            self.assertEqual(st['active'], 'osm', st)
            self.assertIsNone(st['fo'], st)
            self.assertGreaterEqual(st['stats'].get('retry', 0), 4, st)
            b.close()

    def test_a_tile_that_fails_twice_still_counts(self):
        """The retry is once only: OSM down for good still switches to the backup."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            def handle(route):
                if 'tile.openstreetmap.org' in route.request.url:
                    route.abort('connectionreset')
                else:
                    self._osm_ok(route)
            b, pg = self._open(p, '', handle)
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='openfreemap'", secs=20))
            self.assertEqual(pg.evaluate("() => window.TILE_FAILOVER.reason"), 'errors')
            b.close()

    def test_one_or_two_refusals_still_do_not_switch(self):
        """A single 429, or two 403s, must not leave OpenStreetMap. Each refused URL is one request:
        the status fetch is not followed by an image request for the same tile."""
        from collections import Counter
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self._chrome(p)
            for limit, code in ((1, 429), (2, 403)):
                c = b.new_context(viewport={'width': 390, 'height': 844}, service_workers='block', is_mobile=True, has_touch=True)
                pg = c.new_page()
                urls = []
                def on_req(r, box=urls):
                    if 'tile.openstreetmap.org' in r.url:
                        box.append(r.url.split('?')[0])
                pg.on('request', on_req)
                # A phone overview is only a handful of tiles. The first few are 200s, then `limit` refusals.
                mix = self._mix(pg, fail_after=2, bad_limit=limit, switch_on={'on': False}, code=code)
                from site_ready import open_map
                open_map(pg, self.base, stub_tiles=False)
                self.assertTrue(_until(pg, "() => window.TILE_STATS && window.TILE_STATS.error >= %d" % limit, secs=8),
                                pg.evaluate("() => ({active: window.TILE_ACTIVE, stats: window.TILE_STATS})"))
                pg.wait_for_timeout(1200)
                self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm', (limit, code))
                self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"), (limit, code))
                self.assertEqual(len(mix['bad']), limit)
                counts = Counter(u for u in urls if 'tile.openstreetmap.org' in u)
                self.assertTrue(counts, urls[:8])
                self.assertEqual(max(counts.values()), 1, (limit, counts.most_common(3)))
                self.assertEqual(sum(counts[u] for u in mix['bad']), limit, (limit, counts))
                loaded = pg.evaluate("() => document.querySelectorAll('#map .leaflet-tile-loaded').length")
                self.assertGreater(loaded, 3, limit)
                c.close()
            b.close()

    def test_load_and_locate_stay_within_one_request_per_tile(self):
        """Overview plus Locate (Find nearest / the location button). Each OpenStreetMap tile URL is
        requested once. The zoom set is the overview and the results, not every level between them.
        The cap is below a double-fetch of that same view and below a flyTo through the ladder."""
        from collections import Counter
        from playwright.sync_api import sync_playwright
        # Phone screens. iPhone 13 is 390x844, iPhone SE is 375x667. Measured at 10 requests
        # (zoom 5 overview + zoom 13 results, one each). 16 is enough for a slightly taller map
        # and still under a double fetch of that view, and under a grid at every zoom in between.
        cap = 16
        with sync_playwright() as p:
            b = self._chrome(p)
            for width, height in ((390, 844), (375, 667)):
                seen = {'urls': [], 'refs': [], 'methods': []}

                def handle(route):
                    # One parameter: Playwright treats a second parameter as the Request and would
                    # overwrite a default-arg bucket.
                    req = route.request
                    if 'tile.openstreetmap.org' in req.url:
                        seen['urls'].append(req.url.split('?')[0])
                        seen['refs'].append(req.headers.get('referer', ''))
                        if req.method != 'GET':
                            seen['methods'].append(req.method)
                    self._osm_ok(route)

                c = b.new_context(viewport={'width': width, 'height': height}, service_workers='block',
                                  is_mobile=True, has_touch=True,
                                  geolocation={'latitude': 51.539, 'longitude': -0.1426}, permissions=['geolocation'])
                pg = c.new_page()
                pg.route(B.TILE_RE, handle)
                from site_ready import open_map
                open_map(pg, self.base, stub_tiles=False)
                self.assertTrue(_until(pg, "() => document.querySelectorAll('#map .leaflet-tile-loaded').length>3"))
                pg.wait_for_timeout(500)
                z0 = pg.evaluate("() => map.getZoom()")
                pg.click('#me')
                self.assertTrue(_until(pg, "() => map.getZoom() > %d && document.querySelectorAll('#list .card').length >= 1" % z0),
                                pg.evaluate("() => ({z: map.getZoom(), cards: document.querySelectorAll('#list .card').length})"))
                pg.wait_for_timeout(900)  # the 250ms refit, then the tiles for the settled view
                urls, refs, methods = seen['urls'], seen['refs'], seen['methods']
                counts = Counter(urls)
                zooms = sorted({int(u.split('/')[-3]) for u in urls})
                detail = {'size': (width, height), 'requests': len(urls), 'unique': len(counts), 'zooms': zooms,
                          'zoom': pg.evaluate("() => map.getZoom()"), 'most': counts.most_common(3)}
                self.assertTrue(urls, detail)
                self.assertEqual(methods, [], detail)
                self.assertEqual(max(counts.values()), 1, detail)
                self.assertLessEqual(len(zooms), 3, detail)
                self.assertLessEqual(len(urls), cap, detail)
                self.assertGreaterEqual(len(urls), 8, detail)
                origin = 'http://127.0.0.1:%d' % self.srv.server_address[1]
                self.assertTrue(all(r.startswith(origin) for r in refs), refs[:4])
                self.assertEqual(pg.evaluate("() => window.TILE_ACTIVE"), 'osm', detail)
                self.assertIsNone(pg.evaluate("() => window.TILE_FAILOVER || null"), detail)
                painted = pg.evaluate("""() => [...document.querySelectorAll('#map .leaflet-tile-loaded')]
                  .filter(img => (img.getAttribute('data-tile')||'').includes('tile.openstreetmap.org') && img.naturalWidth > 0).length""")
                self.assertGreater(painted, 3, detail)
                c.close()
            b.close()


def _until(pg, js, secs=15):
    """page.evaluate, not wait_for_function: the page CSP blocks the eval that wait_for_function uses."""
    for _ in range(secs * 4):
        if pg.evaluate(js):
            return True
        pg.wait_for_timeout(250)
    return False


def _note(seen, resp):
    if 'tile.openstreetmap.org' not in resp.url:
        return
    if resp.status == 200:
        seen['200'] += 1
    elif resp.status == 403:
        seen['403'] += 1
        try:
            if resp.body()[:8] == b'\x89PNG\r\n\x1a\n':
                seen['png403'] += 1
        except Exception:
            pass


if __name__ == '__main__':
    unittest.main()
