"""WebKit: OpenFreeMap glyph URLs are encoded, and the backup still requests vector tiles.

iOS Safari throws SyntaxError "The string did not match the expected pattern" from
new Request() when a glyph path still has a space ("Noto Sans Regular") or a {token}.
transformRequest hands Request the percent-encoded href. A tile path has neither, so it
is left unchanged.

Playwright's WebKit does not reproduce a blank backup. Checked on main, service worker
blocked, iPhone 13: OSM 429, then Locate, with the real positron style and its tilejson
stubbed — TILE_VECTOR is 'ready' and vector .pbf files are requested. A relative, root
or absolute Worker URL all load. This test does not pretend otherwise.

Rule 23: the style and the vector tile are stand-ins. No public tile host is contacted.
"""
import base64, hashlib, mimetypes, os, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
BASE = 'https://helpmap.uk'
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
# One Mapbox vector tile: a polygon covering the tile, source-layer "water".
PBF = base64.b64decode('GjQKBXdhdGVyEhYSAgAAGAMiDgkAABqAQAAAgED/PwAPGgVjbGFzcyIHCgVvY2VhbiiAIHgC')
STYLE = ('{"version":8,"glyphs":"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",'
         '"sprite":"https://tiles.openfreemap.org/sprites/ofm_f384/ofm",'
         '"sources":{"openmaptiles":{"type":"vector","tiles":'
         '["https://tiles.openfreemap.org/planet/20261025_080012_pt/{z}/{x}/{y}.pbf"],'
         '"minzoom":0,"maxzoom":14}},"layers":['
         '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
         '{"id":"water","type":"fill","source":"openmaptiles","source-layer":"water",'
         '"paint":{"fill-color":"#194b7a"}}]}')
GLYPH = 'https://tiles.openfreemap.org/fonts/Noto Sans Regular/0-255.pbf'
GLYPH_OK = 'https://tiles.openfreemap.org/fonts/Noto%20Sans%20Regular/0-255.pbf'
BRACE = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'
BRACE_OK = 'https://tiles.openfreemap.org/fonts/%7Bfontstack%7D/%7Brange%7D.pbf'
TILE = 'https://tiles.openfreemap.org/planet/20261025_080012_pt/12/2022/1325.pbf'


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def until(pg, js, secs):
    for _ in range(int(secs * 4)):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


class Source(unittest.TestCase):
    def test_glyph_encoding_is_the_only_backup_change_and_the_cache_tag_matches(self):
        with open(os.path.join(R, 'tiles.js'), encoding='utf-8') as fh:
            tiles = fh.read()
        self.assertIn("setWorkerUrl('vendor/maplibre-gl-csp-worker.js')", tiles)
        self.assertNotIn('setWorkerUrl(new URL', tiles)
        self.assertIn('transformRequest: function (url)', tiles)
        self.assertIn("if (!/[ {}]/.test(url)) return;", tiles)
        with open(os.path.join(R, 'tiles.js'), 'rb') as fh:
            tag = 'h' + hashlib.sha256(fh.read()).hexdigest()[:12]
        for rel in ('index.html', 'sw.js'):
            with open(os.path.join(R, rel), encoding='utf-8') as fh:
                self.assertIn('tiles.js?v=' + tag, fh.read(), rel)


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class WebKitVector(unittest.TestCase):
    def test_iphone_13_service_worker_off_encodes_glyphs_and_requests_vector_tiles(self):
        from playwright.sync_api import sync_playwright
        phase = {'bad': False}
        seen = {'pbf': []}
        outside = []
        errs = []

        def local(route):
            url = route.request.url
            path = url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
            f = os.path.join(R, path.lstrip('/'))
            f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f):
                return route.fulfill(status=404, body='')
            with open(f, 'rb') as fh:
                body = fh.read()
            route.fulfill(status=200, body=body, headers={
                'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})

        def osm(route):
            code = 429 if phase['bad'] else 200
            route.fulfill(status=code, content_type='image/png', body=PNG, headers={
                'access-control-allow-origin': '*', 'cache-control': 'no-store', 'x-helpmap-tile': 'stub'})

        def ofm(route):
            url = route.request.url.split('?')[0]
            if '.pbf' in url and '/fonts/' not in url:
                seen['pbf'].append(url)
                return route.fulfill(status=200, content_type='application/x-protobuf', body=PBF, headers={
                    'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
            if '/fonts/' in url:
                return route.fulfill(status=200, content_type='application/x-protobuf', body=b'', headers={
                    'access-control-allow-origin': '*'})
            if '/styles/' in url and 'sprite' not in url:
                return route.fulfill(status=200, content_type='application/json', body=STYLE, headers={
                    'access-control-allow-origin': '*'})
            if url.endswith('.json'):
                return route.fulfill(status=200, content_type='application/json', body='{}', headers={
                    'access-control-allow-origin': '*'})
            if url.endswith('.png'):
                return route.fulfill(status=200, content_type='image/png', body=PNG, headers={
                    'access-control-allow-origin': '*'})
            return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})

        def block(route):
            if route.request.url.startswith('blob:'):
                return route.continue_()
            outside.append(route.request.url[:140])
            route.abort()

        with sync_playwright() as p:
            browser = p.webkit.launch()
            iphone = dict(p.devices['iPhone 13'])
            iphone.pop('default_browser_type', None)
            ctx = browser.new_context(**iphone, service_workers='block',
                                      geolocation={'latitude': 53.4808, 'longitude': -2.2426}, permissions=['geolocation'])
            ctx.route('**/*', block)
            ctx.route('**://tile.openstreetmap.org/**', osm)
            ctx.route('**://*.openfreemap.org/**', ofm)
            ctx.route(BASE + '/**', local)
            ctx.route(BASE + '/', local)
            pg = ctx.new_page()
            pg.on('pageerror', lambda e: errs.append(str(e)[:240]))
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='osm' && document.querySelectorAll('#map img.leaflet-tile-loaded').length>=4", 25),
                            pg.evaluate("() => ({a: window.TILE_ACTIVE, imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length})"))
            phase['bad'] = True
            pg.locator('#me').tap(force=True)
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='openfreemap' && (window.TILE_VECTOR||'')==='ready'", 25),
                            pg.evaluate("() => ({a: window.TILE_ACTIVE, v: window.TILE_VECTOR||null, fo: window.TILE_FAILOVER||null})"))
            got = None
            for _ in range(40):
                if seen['pbf']:
                    got = pg.evaluate("""(args) => {
                      let lyr = null;
                      map.eachLayer(l => { if (l.getMaplibreMap) lyr = l; });
                      const gl = lyr && lyr.getMaplibreMap();
                      const tr = gl && gl._requestManager && gl._requestManager.transformRequest.bind(gl._requestManager);
                      const one = (u) => tr ? tr(u, 'Glyphs').url : null;
                      return {glyph: one(args.glyph), brace: one(args.brace), tile: one(args.tile),
                        worker: (window.maplibregl.getWorkerUrl && window.maplibregl.getWorkerUrl()) || null,
                        fo: window.TILE_FAILOVER || null};
                    }""", {'glyph': GLYPH, 'brace': BRACE, 'tile': TILE})
                    break
                pg.wait_for_timeout(250)
            browser.close()
        self.assertEqual(outside, [], 'request left the stand-in routes')
        syntax = [e for e in errs if 'did not match the expected pattern' in e or 'SyntaxError' in e]
        self.assertEqual(syntax, [], syntax)
        self.assertTrue(seen['pbf'], 'backup reported ready without a vector tile request')
        self.assertTrue(all(u.endswith('.pbf') and '/fonts/' not in u for u in seen['pbf']), seen['pbf'])
        self.assertEqual(got['glyph'], GLYPH_OK, got)
        self.assertEqual(got['brace'], BRACE_OK, got)
        self.assertEqual(got['tile'], TILE, got)
        self.assertEqual(got['worker'], 'vendor/maplibre-gl-csp-worker.js', got)
        fo = got['fo'] or {}
        self.assertEqual((fo.get('from'), fo.get('to'), str(fo.get('reason'))), ('osm', 'openfreemap', '429'), fo)


if __name__ == '__main__':
    unittest.main()
