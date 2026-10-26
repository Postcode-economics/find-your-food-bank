"""Map tile fallback.

The old tiles.js switched only when 6 or more tile errors had arrived and errors also outweighed
successes (bad * 3 > ok). A service-worker or browser cache made most tiles succeed, and the few
uncached ones were HTTP 403 with a PNG body, so that rule never tripped. The trigger now leaves
the provider on any 401, 403 or 429, or on 4 failures inside the last 20 attempts, including after
the first load. OpenStreetMap stays first. Nothing promotes MapTiler on a date.

Checks also stub tile hosts. A page opened with check_browser.new_context must not receive a real
tile-host response.
"""
import functools, http.server, importlib.util, os, re, sys, threading, unittest, urllib.error
from io import BytesIO

R = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(__file__))
import check_browser as B
import tile_monitor as M

CH = '/usr/bin/google-chrome'
HAVE = os.path.exists(CH) and importlib.util.find_spec('playwright') is not None
TILES = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()


def old_rule(ok, bad):
    """The trigger that was in tiles.js: 6 errors, and errors outweigh successes."""
    return bad >= 6 and bad * 3 > ok


class Config(unittest.TestCase):
    def test_osm_is_permanent_default_and_maptiler_is_last(self):
        names = [p['name'] for p in M.providers(TILES)]
        self.assertEqual(names, ['osm', 'stadia', 'maptiler'])
        self.assertEqual({p['name'] for p in M.providers(TILES)}, {'osm', 'stadia', 'maptiler'})
        stadia = next(p for p in M.providers(TILES) if p['name'] == 'stadia')
        paid = next(p for p in M.providers(TILES) if p['name'] == 'maptiler')
        self.assertNotIn('{key}', stadia['url'])
        self.assertEqual(stadia['key'], '')
        self.assertEqual(paid['key'], '')
        self.assertEqual(paid['cap'], 80)
        self.assertIn('{key}', paid['url'])
        self.assertIn('permanent default', TILES)
        self.assertNotIn('2026-11-22', TILES)
        self.assertIsNone(re.search(r'\bDate\b', TILES))
        for rel in ('README.md', 'privacy.html', 'terms.html', 'faq.html', 'scripts/seo_meta.py', 'index.html'):
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            self.assertNotIn('Map © MapTiler © OpenStreetMap', text, rel)
            self.assertNotIn('2026-11-22', text, rel)

    def test_footer_credit_matches_the_welsh_rule(self):
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        footer = re.search(r'<footer>.*?</footer>', home, re.S).group(0)
        node = [p for p in re.split(r'<[^>]+>', footer) if 'OpenStreetMap contributors' in p and 'Built by' in p][0]
        self.assertEqual(node, '). Map © OpenStreetMap contributors. Built by ')
        layers = open(os.path.join(R, 'layers.js'), encoding='utf-8').read()
        self.assertIn(r'/^\)\. Map © OpenStreetMap contributors\. Built by $/', layers)

    def test_old_mix_of_cached_successes_and_a_few_403s_did_not_switch(self):
        # What a mostly-cached view looked like: many 200s, fewer than 6 errors.
        self.assertFalse(old_rule(20, 5))
        self.assertFalse(old_rule(8, 2))
        # Six errors still lost when successes outnumbered them (bad * 3 > ok is 18 > 20).
        self.assertFalse(old_rule(20, 6))
        self.assertTrue(old_rule(10, 6))

    def test_monitor_skips_a_blank_maptiler_key_and_flags_a_403(self):
        called = []

        def opener(req, timeout=0):
            called.append(req.full_url)
            if '403.example' in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 403, 'Invalid key', {}, BytesIO(b'\x89PNG'))
            class R:
                status = 200
                def read(self, n):
                    return b'png'
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return R()

        skipped = M.check_one({'name': 'maptiler', 'url': 'https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={key}', 'key': ''}, open_url=opener)
        self.assertEqual(skipped['status'], 'skipped')
        self.assertFalse(skipped['flag'])
        self.assertEqual(called, [])
        flagged = M.check_one({'name': 'osm', 'url': 'https://403.example/{z}/{x}/{y}.png', 'key': ''}, open_url=opener)
        self.assertEqual(flagged['status'], 403)
        self.assertTrue(flagged['flag'])
        ok = M.check_one({'name': 'stadia', 'url': 'https://tiles.example/{z}/{x}/{y}.png', 'key': ''}, open_url=opener)
        self.assertEqual(ok['status'], 200)
        self.assertFalse(ok['flag'])
        plain = M.request_url({'name': 'stadia', 'url': 'https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png', 'key': ''})
        self.assertNotIn('api_key=', plain)
        keyed = M.request_url({'name': 'stadia', 'url': 'https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png', 'key': 'abc def'})
        self.assertIn('api_key=abc%20def', keyed)
        rows = M.providers()
        self.assertEqual([p['name'] for p in rows], ['osm', 'stadia', 'maptiler'])
        self.assertIsNone(M.request_url(rows[2]))

    def test_real_tile_probe_sends_a_user_agent_and_referer(self):
        seen = {}

        def opener(req, timeout=0):
            seen['ua'] = req.get_header('User-agent')
            seen['referer'] = req.get_header('Referer')
            seen['url'] = req.full_url
            class R:
                status = 200
                def read(self, n):
                    return b'x'
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            return R()

        row = B.one_real_tile(open_url=opener)
        self.assertTrue(row['ok'])
        self.assertEqual(seen['url'], B.TILE_PROBE_URL)
        self.assertIn('helpmap.uk', seen['ua'])
        self.assertEqual(seen['referer'], 'https://helpmap.uk/')
        self.assertNotIn('no-cache', str(seen).lower())

    def test_stub_is_wired_and_real_tiles_env_skips_it(self):
        live = open(os.path.join(R, 'scripts', 'check_browser.py'), encoding='utf-8').read()
        self.assertIn('def stub_map_tiles', live)
        self.assertIn('HELPMAP_REAL_TILES', live)
        self.assertIn('stub_map_tiles(c)', live)
        ready = open(os.path.join(R, 'tests', 'site_ready.py'), encoding='utf-8').read()
        self.assertIn('stub_map_tiles(page)', ready)
        for rel in ('scripts/old_links.py', 'scripts/newlook_parity.py', 'tests/test_updated_dates.py', 'tests/test_webkit_instagram.py', 'tests/newlook_render.py'):
            self.assertIn('stub_map_tiles', open(os.path.join(R, rel), encoding='utf-8').read(), rel)
        old = open(os.path.join(R, 'scripts', 'old_links.py'), encoding='utf-8').read()
        route_at = old.find("c.route('**/*', serve_old)")
        unroute_at = old.find("c.unroute('**/*', serve_old)")
        self.assertGreater(route_at, 0)
        self.assertIn('stub_map_tiles(c)', old[route_at:route_at + 220])
        self.assertIn('stub_map_tiles(c)', old[unroute_at:unroute_at + 220])
        lock = open(os.path.join(R, 'scripts', 'design_lock.py'), encoding='utf-8').read()
        self.assertIn('one_real_tile()', lock)
        self.assertIn('real_tile', lock)
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
        cls.base = 'http://127.0.0.1:%d/?nocount' % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        if HAVE:
            cls.srv.shutdown()

    def setUp(self):
        if not HAVE:
            self.skipTest('needs chrome + playwright')

    def _chrome(self, p):
        return p.chromium.launch(executable_path=CH)

    def test_new_context_makes_no_real_tile_requests(self):
        from playwright.sync_api import sync_playwright
        os.makedirs('/opt/cursor/artifacts/screenshots', exist_ok=True)
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
            self.assertEqual(pinned[-1], 'maptiler')
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
            pg.screenshot(path='/opt/cursor/artifacts/screenshots/map-osm-default.png')
            b.close()

    def _mix(self, page, fail_after, bad_limit, switch_on):
        """OSM: the first fail_after requests are 200, then up to bad_limit distinct URLs are 403
        with a real PNG body (and every repeat of those URLs, including the status probe). The rest
        stay 200. Stadia and any other tile host are 200. switch_on() forces every new OSM tile to 403."""
        state = {'ok': 0, 'bad': set(), 'n403': 0, 'n200': 0}

        def handle(route):
            url = route.request.url.split('?')[0]
            status = 200
            if 'tile.openstreetmap.org' in url:
                if switch_on['on'] or url in state['bad']:
                    status = 403
                    state['bad'].add(url)
                else:
                    state['ok'] += 1
                    if state['ok'] > fail_after and len(state['bad']) < bad_limit:
                        status = 403
                        state['bad'].add(url)
                        state['ok'] -= 1
            if status == 403:
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
        os.makedirs('/opt/cursor/artifacts/screenshots', exist_ok=True)
        with sync_playwright() as p:
            b = self._chrome(p)
            c = b.new_context(viewport={'width': 1100, 'height': 800}, service_workers='block')
            pg = c.new_page()
            seen = {'200': 0, '403': 0, 'png403': 0, 'maptiler': 0, 'stadia': 0}
            pg.on('response', lambda r: _note(seen, r))
            pg.on('request', lambda r: seen.__setitem__('maptiler', seen['maptiler'] + (1 if 'maptiler.com' in r.url else 0)) or seen.__setitem__('stadia', seen['stadia'] + (1 if 'stadiamaps.com' in r.url else 0)))
            mix = self._mix(pg, fail_after=8, bad_limit=2, switch_on={'on': False})
            from site_ready import open_map
            open_map(pg, self.base, stub_tiles=False)
            self.assertTrue(_until(pg, "() => !!(window.TILE_FAILOVER && window.TILE_ACTIVE==='stadia')", secs=8),
                            {'page': pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER, stats: window.TILE_STATS})"),
                             'mix': {k: (list(v) if isinstance(v, set) else v) for k, v in mix.items()},
                             'seen': dict(seen)})
            self.assertTrue(_until(pg, "() => [...document.querySelectorAll('#map .leaflet-tile-loaded')].some(img => img.naturalWidth>0)"))
            fo = pg.evaluate("() => window.TILE_FAILOVER")
            credit = pg.evaluate("() => (document.querySelector('.leaflet-control-attribution')||{}).innerText||''")
            self.assertEqual(fo['from'], 'osm')
            self.assertEqual(fo['to'], 'stadia')
            self.assertGreaterEqual(fo['ok'], 1)
            self.assertLess(fo['bad'], 6)
            self.assertFalse(old_rule(fo['ok'], fo['bad']), fo)
            self.assertEqual(str(fo['reason']), '403')
            self.assertGreaterEqual(seen['200'], 1)
            self.assertGreaterEqual(seen['403'], 1)
            self.assertGreaterEqual(seen['png403'], 1)
            self.assertEqual(seen['maptiler'], 0)
            self.assertGreaterEqual(seen['stadia'], 1)
            self.assertIn('Stadia', credit)
            self.assertIn('OpenStreetMap', credit)
            pg.screenshot(path='/opt/cursor/artifacts/screenshots/map-stadia-fallback.png')
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
            flag['on'] = True
            pg.evaluate("() => map.setView([51.5,-0.12], 13)")
            self.assertTrue(_until(pg, "() => window.TILE_ACTIVE==='stadia'"), pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER})"))
            fo = pg.evaluate("() => window.TILE_FAILOVER")
            self.assertEqual(fo['from'], 'osm')
            self.assertEqual(fo['to'], 'stadia')
            self.assertGreater(state['ok'], 0)
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
