"""OpenFreeMap falls back to OpenStreetMap on a real style failure, with the service worker on.

The grey backup seen in Playwright with service workers blocked is not evidence of a phone bug:
route() answers the style and TileJSON with HTTP 200 image/png, MapLibre throws SyntaxError, and
the canvas stays empty. With the worker allowed, as on a phone, a real style paints and stays.

These checks therefore use a local TLS proxy (nothing is opened to a public host) and
service_workers='allow'. The worker controls the document before the failure is injected.
A fatal style response is HTTP 500 application/json. Intercepting the style with the worker
blocked is not this test.
"""
import os, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


class Source(unittest.TestCase):
    def test_backup_failure_is_wired_to_one_return(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertIn("glMap.on('error'", tiles)
        self.assertIn("glMap.on('load'", tiles)
        self.assertIn("glMap.on('idle'", tiles)
        self.assertIn('function fatalVectorError', tiles)
        self.assertIn('window.TILE_VECTOR_WATCH_MS = 8000', tiles)
        self.assertIn("new Error('no tiles')", tiles)
        self.assertIn("window.TILE_VECTOR = 'loading'", tiles)
        self.assertIn("window.TILE_VECTOR = 'ready'", tiles)
        self.assertNotRegex(tiles, r"addTo\(map\);\s*window\.TILE_VECTOR = 'ready'")
        self.assertIn('vectorFailed = true', tiles)
        self.assertNotIn('transformRequest', tiles)
        # A blocked worker plus Playwright interception is not how this fallback is proved.
        src = open(os.path.abspath(__file__), encoding='utf-8').read()
        self.assertNotIn('service_workers=' + "'block'", src)
        self.assertNotIn('page.' + 'route(', src)


def _state(pg):
    return pg.evaluate("""() => ({
      a: window.TILE_ACTIVE || '',
      v: window.TILE_VECTOR || '',
      back: (window.TILE_FAILOVER || {}).back || null,
      canvas: !!document.querySelector('#map canvas.maplibregl-canvas, #map .leaflet-gl-layer canvas'),
      sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
      painted: [...document.querySelectorAll('#map img.leaflet-tile-loaded')].filter(i =>
        (i.getAttribute('data-tile') || i.src).includes('tile.openstreetmap.org') && i.naturalWidth > 0).length
    })""")


class ProxyBase:
    """Filled in by the browser tests so importing this module does not load the journey proxy."""


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class FallbackWithWorkerOn(unittest.TestCase):
    def _browser(self, proxy):
        import test_iphone_journeys as J
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.webkit.launch()
        dev = dict(p.devices['iPhone 13'])
        dev.pop('default_browser_type', None)
        ctx = browser.new_context(**dev, proxy={'server': proxy.url}, ignore_https_errors=True,
                                  service_workers='allow', geolocation=J.HERE, permissions=['geolocation'])
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)[:180]))
        pg.goto(J.BASE + '/?nocount', wait_until='domcontentloaded', timeout=30000)
        self.assertTrue(J._until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 25))
        self.assertTrue(J._until(pg, "() => window.TILE_ACTIVE==='osm'", 20), _state(pg))
        return p, browser, pg, errs, J

    def test_style_500_returns_to_osm_and_paints(self):
        import test_iphone_journeys as J

        class Proxy(J.Proxy):
            def __init__(self):
                super().__init__()
                self.osm = 'ok'
                self.ofm_fail = False

            def _answer(self, host, path):
                if self.ofm_fail and host == 'tiles.openfreemap.org' and (
                        '/styles/' in path or path.endswith('.json') or '/sprites/' in path):
                    self.hits['ofm_style'] = self.hits.get('ofm_style', 0) + 1
                    self.osm = 'ok'
                    return J._http(500, 'Server Error', b'{"message":"injected style failure"}',
                                   'application/json', 'no-store')
                return J.Proxy._answer(self, host, path)

        proxy = Proxy()
        try:
            p, browser, pg, errs, J = self._browser(proxy)
            try:
                pg.evaluate("async () => { await caches.delete('fyfb-tiles2'); }")
                proxy.hits = {'osm': 0, 'ofm_style': 0, 'ofm_pbf': 0}
                proxy.osm = 'refuse'
                proxy.ofm_fail = True
                pg.reload(wait_until='domcontentloaded', timeout=30000)
                self.assertTrue(J._until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 15))
                end = None
                for _ in range(80):
                    st = _state(pg)
                    if st['a'] == 'osm' and str(st['v']).startswith('failed') and st['painted'] >= 4 and not st['canvas'] and st['sw']:
                        end = st
                        break
                    pg.wait_for_timeout(250)
                self.assertIsNotNone(end, (_state(pg), dict(proxy.hits), errs[:3], proxy.other[:4]))
                self.assertEqual(end['back'], 'osm', end)
                self.assertGreaterEqual(proxy.hits.get('ofm_style', 0), 1)
                self.assertEqual(errs, [], errs)
                self.assertEqual(proxy.other, [], proxy.other[:4])
            finally:
                browser.close()
                p.stop()
        finally:
            proxy.stop()

    def test_real_style_stays_ready_past_the_watchdog(self):
        import test_iphone_journeys as J

        class Proxy(J.Proxy):
            def __init__(self):
                super().__init__()
                self.osm = 'ok'
                self.mode = 'prime'
                self._refused = 0

            def _answer(self, host, path):
                if self.mode == 'backup' and (host == 'tile.openstreetmap.org' or host.endswith('.tile.openstreetmap.org')):
                    self.hits['osm'] = self.hits.get('osm', 0) + 1
                    self._refused += 1
                    if self._refused <= 6:
                        return J._http(429, 'Too Many Requests', J.TILE_REFUSED, 'image/png', 'no-store')
                    return J._http(200, 'OK', J.TILE_OK, 'image/png', 'public, max-age=86400')
                return J.Proxy._answer(self, host, path)

        proxy = Proxy()
        try:
            p, browser, pg, errs, J = self._browser(proxy)
            try:
                pg.evaluate("async () => { await caches.delete('fyfb-tiles2'); }")
                proxy.hits = {'osm': 0, 'ofm_style': 0, 'ofm_pbf': 0}
                proxy.mode = 'backup'
                pg.reload(wait_until='domcontentloaded', timeout=30000)
                self.assertTrue(J._until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 15))
                ready = J._until(pg, "() => window.TILE_ACTIVE==='openfreemap' && window.TILE_VECTOR==='ready'", 20)
                self.assertTrue(ready, (_state(pg), dict(proxy.hits), errs[:3]))
                pg.wait_for_timeout(9000)
                later = _state(pg)
                self.assertEqual(later['a'], 'openfreemap', later)
                self.assertEqual(later['v'], 'ready', later)
                self.assertTrue(later['canvas'], later)
                self.assertGreaterEqual(proxy.hits.get('ofm_pbf', 0), 1, proxy.hits)
                self.assertEqual(errs, [])
                self.assertEqual(proxy.other, [])
            finally:
                browser.close()
                p.stop()
        finally:
            proxy.stop()
