"""Opt-in offline tiles (rules 23 and 26): with HELPMAP_OFFLINE_TILES set, the browser checks get map
tiles from a local server and send zero requests to public tile hosts. Without it, nothing changes."""
import functools, http.server, os, struct, sys, threading, unittest, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import check_browser as B
import offline_tiles as T
ROOT = os.path.join(os.path.dirname(__file__), '..')


def _png():
    raw = b''.join(b'\x00' + b'\xee\xee\xe6' * 256 for _ in range(256))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class Units(unittest.TestCase):
    def test_default_is_off(self):
        self.assertIsNone(T.base_url({}))
        self.assertIsNone(T.base_url({T.ENV: '  '}))
        self.assertEqual(T.base_url({T.ENV: 'http://127.0.0.1:8091/'}), 'http://127.0.0.1:8091')

    def test_default_context_routes_only_to_the_stand_in_tiles(self):
        # Rule 23 (PR 165) + PR 157: a default context has exactly one route, the stand-in tiles, covering every
        # public tile host, and a tile request there never reaches the network. With HELPMAP_OFFLINE_TILES set,
        # the offline map replaces the stand-in (still exactly one route, and not the stub).
        class Ctx:
            def __init__(s): s.routes = []
            def route(s, *a): s.routes.append(a)
            def on(s, *a): pass
            def set_default_timeout(s, t): pass
            def set_default_navigation_timeout(s, t): pass
        class Br:
            def new_context(s, **kw): return Ctx()
        class R:
            def __init__(s, u): s.request = type('Q', (), {'url': u})(); s.out = None
            def fulfill(s, **kw): s.out = kw
            def abort(s, *a): s.out = 'abort'
            def continue_(s, *a, **kw): raise AssertionError('tile request reached the network: ' + s.request.url)
            def fallback(s, *a, **kw): raise AssertionError('tile request fell through to the network: ' + s.request.url)
            def fetch(s, *a, **kw): raise AssertionError('tile request fetched from the network: ' + s.request.url)
        saved = {k: os.environ.pop(k, None) for k in (T.ENV, 'HELPMAP_REAL_TILES')}
        try:
            c = B.new_context(Br())
            self.assertEqual(len(c.routes), 1, c.routes)
            pat, handler = c.routes[0][0], c.routes[0][1]
            self.assertIs(pat, B.TILE_RE)
            for h in T.EXTERNAL_TILE_HOSTS:
                u = 'https://%s/6/31/20.png' % h
                self.assertTrue(pat.match(u), 'stand-in route does not cover ' + h)
                r = R(u); handler(r)
                self.assertIsInstance(r.out, dict, u)
                self.assertEqual(r.out['status'], 200, u)
                self.assertEqual(r.out['headers'].get('x-helpmap-tile'), 'stub', u)
                self.assertTrue(r.out['body'].startswith(b'\x89PNG'), u)
            # A style or tilejson on that host is not the PNG placeholder (the WebKit grey-map artefact).
            for doc in ('https://tiles.openfreemap.org/styles/positron',
                        'https://tiles.openfreemap.org/planet/tilejson.json'):
                style = R(doc)
                handler(style)
                body = (style.out or {}).get('body') or b''
                self.assertFalse(body.startswith(b'\x89PNG'), doc)
                self.assertNotEqual((style.out or {}).get('content_type'), 'image/png', doc)
                self.assertEqual((style.out or {}).get('status'), 404, doc)
            os.environ[T.ENV] = 'http://127.0.0.1:9'
            c = B.new_context(Br())
            self.assertEqual(len(c.routes), 1, c.routes)
            self.assertIsNot(c.routes[0][0], B.TILE_RE)  # the offline map, not the stand-in
            self.assertIsNot(c.routes[0][1], handler)
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None: os.environ[k] = v

    def test_blank_fallback_answers_without_a_server(self):
        class R:
            def __init__(s, u): s.request = type('Q', (), {'url': u})(); s.out = None
            def fulfill(s, **kw): s.out = kw
            def abort(s): s.out = 'abort'
        class Ctx:
            def route(s, pat, h): s.h = h
            def on(s, *a): pass
        c = Ctx(); st = T.attach(c, 'blank'); r = R('https://tile.openstreetmap.org/6/31/20.png'); c.h(r)
        self.assertEqual(r.out['status'], 200); self.assertTrue(r.out['body'].startswith(b'\x89PNG'))
        self.assertEqual((st.served, st.external), (1, []))

    def test_strict_flags_other_tile_hosts(self):
        class Ctx:
            def route(s, pat, h): pass
            def on(s, ev, f): s.f = f
        c = Ctx(); st = T.attach(c, 'blank')
        for u in ('https://tile.openstreetmap.org/1/0/0.png', 'https://helpmap.uk/icon-192.png',
                  'http://127.0.0.1:8091/styles/bright/256/1/0/0.png'):
            c.f(type('Q', (), {'url': u})())
        self.assertEqual(st.external, [])
        c.f(type('Q', (), {'url': 'https://maps.example.net/7/63/42.png'})())
        self.assertEqual(st.external, ['https://maps.example.net/7/63/42.png'])
        st.external.clear()

    def test_tile_url_mapping(self):
        b = 'http://127.0.0.1:8091'
        self.assertEqual(T.local_tile_url('https://tile.openstreetmap.org/6/31/20.png', b),
                         b + '/styles/bright/256/6/31/20.png')
        self.assertEqual(T.local_tile_url('https://api.maptiler.com/maps/streets-v2/256/7/63/42.png?key=x', b),
                         b + '/styles/bright/256/7/63/42.png')
        self.assertIsNone(T.local_tile_url('https://api.maptiler.com/maps/streets-v2/style.json?key=x', b))
        for h in ('https://tile.openstreetmap.org/1/0/0.png', 'https://a.tile.openstreetmap.org/1/0/0.png',
                  'https://tiles.stadiamaps.com/tiles/osm_bright/1/0/0.png', 'https://tiles.openfreemap.org/x'):
            self.assertTrue(T.is_external_tile_host(h), h)
        self.assertFalse(T.is_external_tile_host('https://helpmap.uk/tile.openstreetmap.org/1/0/0.png'))
        self.assertFalse(T.is_external_tile_host('http://127.0.0.1:8091/styles/bright/256/1/0/0.png'))


class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception: raise unittest.SkipTest('playwright not installed')
        if not os.path.exists('/usr/bin/google-chrome'): raise unittest.SkipTest('no chrome')
        site = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        site.log_message = lambda *a: None
        cls.site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), site)
        png, hits = _png(), []
        class Tiles(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                ok = self.path.startswith('/styles/bright/256/') and self.path.endswith('.png')
                self.send_response(200 if ok else 404); self.send_header('content-type', 'image/png'); self.end_headers()
                if ok: self.wfile.write(png)
            def log_message(self, *a): pass
        cls.hits = hits
        cls.tiles = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Tiles)
        for s in (cls.site, cls.tiles): threading.Thread(target=s.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.site.shutdown(); cls.tiles.shutdown()

    def test_zero_external_tile_requests(self):
        from playwright.sync_api import sync_playwright
        os.environ[T.ENV] = 'http://127.0.0.1:%d' % self.tiles.server_address[1]
        site = 'http://127.0.0.1:%d' % self.site.server_address[1]
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path='/usr/bin/google-chrome')
                c = B.new_context(b, viewport={'width': 1366, 'height': 900})
                stats = c.offline_tile_stats
                # Anything else off-box (analytics, postcodes) is cut, so only the two local servers answer.
                c.route(lambda u: not u.startswith(site) and not T.is_external_tile_host(u), lambda r: r.abort())
                # Every tile-host request the page makes must be one our route answered locally.
                seen = []
                c.on('request', lambda r: T.is_external_tile_host(r.url) and seen.append(r.url))
                pg = c.new_page()
                pg.goto(site + '/index.html?fresh=1', wait_until='domcontentloaded')
                pg.wait_for_function("()=>document.querySelectorAll('#map .leaflet-tile-loaded').length>=4", timeout=30000)
                loaded = pg.evaluate("()=>document.querySelectorAll('#map .leaflet-tile-loaded').length")
                pg.wait_for_timeout(500)
                b.close()
        finally:
            os.environ.pop(T.ENV, None)
        self.assertGreaterEqual(loaded, 4)
        self.assertGreaterEqual(stats.served, 4)
        self.assertGreaterEqual(len(self.hits), stats.served)
        self.assertEqual(stats.external, [])
        self.assertEqual(len(seen), stats.served + stats.failed, 'a tile request reached a public tile host')
        self.assertEqual(stats.failed, 0)


if __name__ == '__main__':
    unittest.main()
