"""iOS Safari and Instagram's in-app browser (WKWebView) reject img.decode() for a tile that loaded.

Dean, 27 Oct 2026, live v91: the debug line was loaded 10, errors 4, codes decode,decode,decode,decode,
and the map switched to OpenFreeMap. A decode() rejection must not count when
img.complete && naturalWidth > 0. A broken image (naturalWidth 0) still records 'decode'.
The 4-in-20 rule is unchanged. Tile hosts are stubbed. Nothing here contacts a public tile server.
"""
import hashlib, mimetypes, os, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
BASE = 'https://helpmap.uk'
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
OFM = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
       '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
       '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}}]}')
IG = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
      'Mobile/15E148 Instagram 330.0.0.0 (iPhone14,5; iOS 17_4; en_GB; en-GB; scale=3.00; 1170x2532; 600000000) helpmap-check')
REJECT = """HTMLImageElement.prototype.decode = function () {
  window.__hmDecodeRejects = (window.__hmDecodeRejects || 0) + 1;
  return Promise.reject(new DOMException('The source image cannot be decoded.', 'EncodingError'));
};"""


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def until(pg, js, secs=25):
    for _ in range(secs * 4):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


class Source(unittest.TestCase):
    def test_loaded_bitmap_is_not_a_decode_failure_and_the_window_is_unchanged(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        self.assertIn('img.complete && img.naturalWidth > 0', tiles)
        self.assertIn("codes.push('decode')", tiles)
        self.assertIn('window.TILE_WINDOW = 20;', tiles)
        self.assertIn('window.TILE_WINDOW_FAILS = 4;', tiles)
        self.assertIn('window.TILE_WINDOW_REFUSALS = 3;', tiles)
        self.assertIn("typeof img.decode !== 'function'", tiles)
        tag = 'tiles.js?v=h' + hashlib.sha256(tiles.encode()).hexdigest()[:12]
        self.assertIn(tag, home)
        self.assertIn(tag, sw)
        self.assertIn("const C='fyfb-v97'", sw)
        self.assertIn('content="fyfb-v97"', home)


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class WebKit(unittest.TestCase):
    def _open(self, p, ua=None, reject=True, body=None):
        iphone = dict(p.devices['iPhone 13'])
        iphone.pop('default_browser_type', None)
        if ua:
            iphone['user_agent'] = ua
        b = p.webkit.launch()
        c = b.new_context(**iphone, service_workers='allow')
        if reject:
            c.add_init_script(REJECT)

        def local(route):
            path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
            f = os.path.join(R, path.lstrip('/'))
            f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f):
                return route.fulfill(status=404, body='')
            route.fulfill(status=200, body=open(f, 'rb').read(), headers={
                'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})

        def tile(route):
            route.fulfill(status=200, content_type='image/png', body=body if body is not None else PNG, headers={
                'access-control-allow-origin': '*', 'cache-control': 'public, max-age=86400'})

        c.route(BASE + '/**', local)
        c.route(BASE + '/', local)
        c.route('**://tile.openstreetmap.org/**', tile)
        c.route('**://*.openfreemap.org/**', lambda r: r.fulfill(
            status=200, content_type='application/json', body=OFM, headers={'access-control-allow-origin': '*'}))
        pg = c.new_page()
        pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
        return b, pg

    def _state(self, pg):
        return pg.evaluate("""() => ({
          active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null,
          error: (window.TILE_STATS || {}).error || 0, load: (window.TILE_STATS || {}).load || 0,
          fails: window.TILE_WINDOW_FAILS, window: window.TILE_WINDOW,
          rejects: window.__hmDecodeRejects || 0,
          painted: [...document.querySelectorAll('#map img.leaflet-tile-loaded')].filter(i => i.naturalWidth > 0).length,
          ua: navigator.userAgent
        })""")

    def test_decode_rejection_on_a_loaded_tile_does_not_switch(self):
        from playwright.sync_api import sync_playwright
        ready = """() => window.TILE_ACTIVE==='osm' && !window.TILE_FAILOVER
          && window.TILE_STATS && window.TILE_STATS.error === 0 && (window.__hmDecodeRejects || 0) >= 4
          && [...document.querySelectorAll('#map img.leaflet-tile-loaded')].filter(i => i.naturalWidth > 0).length >= 4"""
        with sync_playwright() as p:
            b, pg = self._open(p)
            self.assertTrue(until(pg, ready), self._state(pg))
            st = self._state(pg)
            self.assertEqual(st['active'], 'osm', st)
            self.assertIsNone(st['fo'], st)
            self.assertEqual(st['error'], 0, st)
            self.assertGreaterEqual(st['painted'], 4, st)
            self.assertGreaterEqual(st['rejects'], 4, st)
            self.assertEqual(st['fails'], 4, st)
            self.assertEqual(st['window'], 20, st)
            self.assertIn('no switch', pg.evaluate("() => document.getElementById('tiles-debug').innerText"))
            b.close()

    def test_instagram_wkwebview_decode_rejection_does_not_switch(self):
        from playwright.sync_api import sync_playwright
        ready = """() => window.TILE_ACTIVE==='osm' && !window.TILE_FAILOVER
          && window.TILE_STATS && window.TILE_STATS.error === 0 && (window.__hmDecodeRejects || 0) >= 4
          && [...document.querySelectorAll('#map img.leaflet-tile-loaded')].filter(i => i.naturalWidth > 0).length >= 4"""
        with sync_playwright() as p:
            b, pg = self._open(p, ua=IG)
            self.assertTrue(until(pg, ready), self._state(pg))
            st = self._state(pg)
            self.assertIn('Instagram 330', st['ua'])
            self.assertEqual(st['active'], 'osm', st)
            self.assertIsNone(st['fo'], st)
            self.assertEqual(st['error'], 0, st)
            self.assertGreaterEqual(st['painted'], 4, st)
            self.assertGreaterEqual(st['rejects'], st['painted'], st)
            b.close()

    def test_broken_image_still_records_decode(self):
        """naturalWidth 0 still counts as code 'decode' and still trips the unchanged 4-in-20 rule."""
        from playwright.sync_api import sync_playwright
        ready = """() => window.TILE_FAILOVER && window.TILE_FAILOVER.reason==='errors'
          && window.TILE_STATS && window.TILE_STATS.error >= 4
          && (window.TILE_FAILOVER.codes || []).indexOf('decode') >= 0"""
        with sync_playwright() as p:
            b, pg = self._open(p, reject=False, body=b'\x00not-a-png')
            self.assertTrue(until(pg, ready), self._state(pg))
            st = self._state(pg)
            self.assertGreaterEqual(st['error'], 4, st)
            self.assertEqual(st['fo']['reason'], 'errors', st)
            self.assertGreaterEqual(st['fo']['bad'], 4, st)
            self.assertTrue(all(c == 'decode' for c in st['fo']['codes']), st)
            self.assertEqual(st['fails'], 4, st)
            self.assertEqual(st['window'], 20, st)
            b.close()


if __name__ == '__main__':
    unittest.main()
