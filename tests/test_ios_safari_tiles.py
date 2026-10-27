"""iPhone Safari must keep the OpenStreetMap image tiles (27 Oct 2026).

PR 165 read every OSM tile with fetch() before setting the <img>. The service worker caches
<img> tiles as opaque responses. WebKit rejects that body for a CORS fetch ("Response served by
service worker is opaque"), tiles.js counted the throw as a tile failure, and after four throws
the map left OpenStreetMap for the OpenFreeMap MapLibre layer. That layer is the pale map, the
OpenFreeMap credit, the slow open, the scroll lag and the dead taps.

These checks use Playwright's WebKit with an iPhone profile. Tile hosts are stubbed. Nothing
here contacts a public tile server.
"""
import mimetypes, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
R = os.path.join(os.path.dirname(__file__), '..')
BASE = 'https://helpmap.uk'
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
OFM = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
       '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
       '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
       '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def local(route):
    path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
    f = os.path.join(R, path.lstrip('/'))
    f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
    if not os.path.isfile(f):
        return route.fulfill(status=404, body='')
    route.fulfill(status=200, body=open(f, 'rb').read(), headers={
        'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream',
        'cache-control': 'no-store'})


def until(pg, js, secs=20):
    for _ in range(secs * 4):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


def png(route):
    route.fulfill(status=200, content_type='image/png', body=PNG, headers={
        'access-control-allow-origin': '*',
        'cache-control': 'public, max-age=86400',
        'x-helpmap-tile': 'stub'})


def ofm(route):
    route.fulfill(status=200, content_type='application/json', body=OFM, headers={
        'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})


class Source(unittest.TestCase):
    def test_probe_cannot_block_the_image_and_the_worker_will_not_return_opaque_to_it(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        css = open(os.path.join(R, 'header.css'), encoding='utf-8').read()
        self.assertIn("credentials: 'omit'", tiles)
        self.assertNotIn('img.crossOrigin', tiles)
        self.assertNotIn('crossOrigin: true', tiles)
        self.assertIn('reveal()', tiles)
        # A cached opaque tile is returned, not refetched. A refetch would hit the network while offline.
        self.assertIn('if(hit)return hit', sw)
        self.assertNotIn("e.request.mode!=='no-cors'", sw)
        self.assertNotIn('maplibre-gl', home)
        self.assertIn('#map .leaflet-gl-layer,#map .leaflet-gl-layer *{pointer-events:none!important}', home)
        self.assertIn('pointer-events:none!important', css)
        self.assertIn('tiles.js?v=ios20261027', home)
        self.assertIn('tiles.js?v=ios20261027', sw)


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class IPhone(unittest.TestCase):
    def _browser(self, p, sw):
        iphone = dict(p.devices['iPhone 13'])
        iphone.pop('default_browser_type', None)
        b = p.webkit.launch()
        c = b.new_context(**iphone, color_scheme='dark', service_workers='allow' if sw else 'block')
        c.route(BASE + '/**', local)
        c.route(BASE + '/', local)
        return b, c

    def test_opaque_cached_tiles_stay_openstreetmap_without_a_refetch(self):
        """Returning iPhone: the worker holds opaque OSM tiles. The status fetch throws. The map still
        paints those images and does not load MapLibre or ask the tile host again."""
        from playwright.sync_api import sync_playwright
        seen = {'n': 0, 'urls': []}

        def tiles(route):
            seen['n'] += 1
            seen['urls'].append(route.request.url.split('?')[0])
            if 'openfreemap.org' in route.request.url:
                return ofm(route)
            return png(route)

        with sync_playwright() as p:
            b, c = self._browser(p, True)
            c.route('**://tile.openstreetmap.org/**', tiles)
            c.route('**://*.openfreemap.org/**', tiles)
            pg = c.new_page()
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)"),
                            'service worker did not take control')
            seeded = pg.evaluate("""async () => {
              if (map && map._hmTileStop) map._hmTileStop();
              await caches.delete('fyfb-tiles');
              const urls = [];
              for (let x = 13; x <= 17; x++) for (let y = 8; y <= 12; y++) urls.push('https://tile.openstreetmap.org/5/' + x + '/' + y + '.png');
              await Promise.all(urls.map(u => new Promise(res => { const i = new Image(); i.onload = i.onerror = () => res(); i.src = u; })));
              const cache = await caches.open('fyfb-tiles');
              let opaque = 0;
              for (let n = 0; n < 30 && opaque < urls.length; n++) {
                opaque = 0;
                for (const u of urls) { const hit = await cache.match(u); if (hit && hit.type === 'opaque') opaque++; }
                if (opaque < urls.length) await new Promise(r => setTimeout(r, 50));
              }
              return {opaque, want: urls.length};
            }""")
            self.assertEqual(seeded['opaque'], seeded['want'], seeded)
            # From here the tile host refuses everyone. A painted tile can only be the opaque copy.
            c.unroute('**://tile.openstreetmap.org/**', tiles)

            def deny(route):
                seen['n'] += 1
                seen['urls'].append(route.request.url.split('?')[0])
                route.abort('failed')

            c.route('**://tile.openstreetmap.org/**', deny)
            seen['n'] = 0
            seen['urls'].clear()
            pg.evaluate("() => { map._hmTileStop(); addTiles(map); }")
            self.assertTrue(until(pg, """() => window.TILE_ACTIVE==='osm'
              && document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4
              && [...document.querySelectorAll('#map img.leaflet-tile-loaded')].every(i => i.naturalWidth > 0)
              && !window.maplibregl && !window.TILE_FAILOVER"""),
                            pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER||null, lib: !!window.maplibregl, imgs: document.querySelectorAll('#map img.leaflet-tile').length, net: %d})" % seen['n']))
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate('window.TILE_ACTIVE'), 'osm')
            self.assertFalse(pg.evaluate('!!window.maplibregl'))
            self.assertEqual(seen['n'], 0, seen['urls'][:8])
            b.close()

    def test_iphone_keeps_osm_images_when_the_script_fetch_fails(self):
        """What iOS does: the status fetch fails, the <img> would succeed. Stay on OpenStreetMap.
        MapLibre stays unloaded, so the page is not the pale backup and taps still land on buttons."""
        from playwright.sync_api import sync_playwright
        seen = {'fetch': 0, 'image': 0}

        def tiles(route):
            url = route.request.url
            if 'openfreemap.org' in url:
                return ofm(route)
            if 'openstreetmap.org' not in url:
                return route.abort('failed')
            dest = route.request.headers.get('sec-fetch-dest') or ''
            if dest == 'image' or route.request.resource_type == 'image':
                seen['image'] += 1
                return png(route)
            seen['fetch'] += 1
            return route.abort('failed')

        with sync_playwright() as p:
            b, c = self._browser(p, False)
            c.route('**://tile.openstreetmap.org/**', tiles)
            c.route('**://*.openfreemap.org/**', tiles)
            pg = c.new_page()
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, """() => window.TILE_ACTIVE==='osm'
              && document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4
              && [...document.querySelectorAll('#map img.leaflet-tile-loaded')].every(i => i.src.includes('tile.openstreetmap.org') && i.naturalWidth > 0)
              && !window.maplibregl && !window.TILE_FAILOVER"""),
                            pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER||null, stats: window.TILE_STATS||null, lib: !!window.maplibregl, imgs: document.querySelectorAll('#map img.leaflet-tile').length})"))
            pg.wait_for_timeout(600)
            state = pg.evaluate("""() => ({
              active: window.TILE_ACTIVE,
              fo: window.TILE_FAILOVER || null,
              lib: !!window.maplibregl,
              gl: !!document.querySelector('#map .leaflet-gl-layer'),
              credit: (document.querySelector('.leaflet-control-attribution') || {}).innerText || '',
              filter: getComputedStyle(document.querySelector('#map .leaflet-tile-pane')).filter,
              light: document.documentElement.classList.contains('light'),
              cross: [...document.querySelectorAll('#map img.leaflet-tile')].some(i => i.crossOrigin)
            })""")
            self.assertEqual(state['active'], 'osm', state)
            self.assertIsNone(state['fo'], state)
            self.assertFalse(state['lib'], state)
            self.assertFalse(state['gl'], state)
            self.assertFalse(state['cross'], state)
            self.assertIn('OpenStreetMap', state['credit'])
            self.assertNotIn('OpenFreeMap', state['credit'])
            self.assertEqual(state['filter'], 'none', state)
            self.assertFalse(state['light'])
            self.assertGreaterEqual(seen['image'], 4, seen)
            self.assertGreaterEqual(seen['fetch'], 1, seen)
            pg.evaluate("() => { window.__go = 0; document.querySelector('button.go').addEventListener('click', e => { e.preventDefault(); window.__go++; }, true); }")
            pg.locator('button.go').tap()
            self.assertGreaterEqual(pg.evaluate('window.__go'), 1)
            pg.locator('#share').scroll_into_view_if_needed()
            hit = pg.evaluate("""() => { const el = document.getElementById('share'); const r = el.getBoundingClientRect();
              const h = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return h && (h.id || h.className || h.tagName); }""")
            self.assertEqual(hit, 'share', hit)
            b.close()

    def test_openfreemap_canvas_does_not_take_taps(self):
        """A real failover still loads MapLibre, and its padded canvas must not cover the buttons."""
        from playwright.sync_api import sync_playwright

        def tiles(route):
            if 'openfreemap.org' in route.request.url:
                return ofm(route)
            return route.abort('failed')

        with sync_playwright() as p:
            b, c = self._browser(p, False)
            c.route('**://tile.openstreetmap.org/**', tiles)
            c.route('**://*.openfreemap.org/**', tiles)
            pg = c.new_page()
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='openfreemap' && !!document.querySelector('#map .leaflet-gl-layer')"),
                            pg.evaluate("() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER||null, v: window.TILE_VECTOR||null})"))
            pe = pg.evaluate("""() => ({
              layer: getComputedStyle(document.querySelector('#map .leaflet-gl-layer')).pointerEvents,
              canvas: getComputedStyle(document.querySelector('#map .leaflet-gl-layer canvas')).pointerEvents,
              filter: getComputedStyle(document.querySelector('#map .leaflet-gl-layer')).filter
            })""")
            self.assertEqual(pe['layer'], 'none', pe)
            self.assertEqual(pe['canvas'], 'none', pe)
            self.assertEqual(pe['filter'], 'none', pe)
            pg.evaluate("() => { window.__go = 0; document.querySelector('button.go').addEventListener('click', e => { e.preventDefault(); window.__go++; }, true); }")
            pg.locator('button.go').tap()
            self.assertGreaterEqual(pg.evaluate('window.__go'), 1)
            z = pg.evaluate('map.getZoom()')
            pg.locator('.leaflet-control-zoom-in').tap()
            pg.wait_for_timeout(700)
            self.assertEqual(pg.evaluate('map.getZoom()'), z + 1)
            b.close()


if __name__ == '__main__':
    unittest.main()
