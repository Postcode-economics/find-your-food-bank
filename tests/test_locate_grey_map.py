"""Grey map after 'Find nearest food bank' / the location button (Dean's iPhone, 27 Oct 2026).

Opening the map was in colour; pressing either button turned it grey. Both buttons jump the map to a new area,
which asks OpenStreetMap for a batch of tiles that are not cached. tiles.js fetched every tile twice (a status
fetch, then the <img>), doubling that burst, and 3 refusals (429/403) inside the last 20 switch to the
OpenFreeMap backup, whose 'positron' style is light grey. If that style or its sources then failed, nothing
noticed: TILE_VECTOR said 'ready' before MapLibre had drawn, with no error listener and no watchdog, so the map
could stay an empty grey box with no way back.

These WebKit iPhone 13 checks press both buttons (geolocation granted) with the service worker on and off and
with the backup forced, and require the map to be painted afterwards. Tile hosts are stubbed (rule 23).
"""
import os, sys, unittest, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_iphone_map_fix import HAVE, BASE, until, R  # noqa: E402

SHOTS = os.environ.get('HELPMAP_SHOTS') or os.path.join(__import__('tempfile').gettempdir(), 'helpmap-shots')


def _png(rgb):
    raw = b''.join(b'\x00' + bytes(rgb) * 256 for _ in range(256))
    c = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + c(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0)) + c(b'IDAT', zlib.compress(raw, 9)) + c(b'IEND', b'')


GREEN = (0xa8, 0xd0, 0x8d)
TILE = _png(GREEN)
STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
         '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
         '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
         '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
# WebKit does not route a service worker's own fetches through Playwright, so with the worker on the stand-in tiles
# are answered inside the worker: its fetch() is wrapped for tile hosts only, and sw.js's own tile handling still runs.
SW_STUB = ("""const __hmTile = Uint8Array.from(atob('%s'), c => c.charCodeAt(0)); let __hmRefuse = false;
self.addEventListener('message', e => { if (e.data && e.data.hmStub) __hmRefuse = e.data.hmStub === 'refuse'; });
const __hmFetch = self.fetch.bind(self);
self.fetch = function (req, opt) { const u = new URL(typeof req === 'string' ? req : req.url);
  if (u.host === 'tile.openstreetmap.org' || u.host.endsWith('.tile.openstreetmap.org')) return Promise.resolve(__hmRefuse
    ? new Response('rate limited', {status: 429, headers: {'access-control-allow-origin': '*'}})
    : new Response(__hmTile, {status: 200, headers: {'content-type': 'image/png', 'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'}}));
  return __hmFetch(req, opt); };
""" % __import__('base64').b64encode(TILE).decode()).encode()
SPOTS = {'littlehampton': (50.81, -0.54), 'manchester': (53.48, -2.24)}

# OSM painted: at least 4 loaded tiles inside the visible map box, every one decoded with our green stub pixels.
OSM_PAINTED = """async () => {
  if (window.TILE_ACTIVE !== 'osm') return false;
  const m = document.getElementById('map').getBoundingClientRect();
  const imgs = [...document.querySelectorAll('#map img.leaflet-tile-loaded')].filter(i => { const b = i.getBoundingClientRect();
    return b.right > m.left && b.left < m.right && b.bottom > m.top && b.top < m.bottom && i.naturalWidth > 0; });
  if (imgs.length < 4) return false;
  if (!imgs.every(i => (i.dataset.src || i.src).includes('tile.openstreetmap.org'))) return false;
  const cv = document.createElement('canvas'); cv.width = cv.height = 1; const g = cv.getContext('2d');
  for (const i of imgs) { try { g.clearRect(0, 0, 1, 1); g.drawImage(i, 128, 128, 1, 1, 0, 0, 1, 1); const d = g.getImageData(0, 0, 1, 1).data;
    if (Math.abs(d[0] - 168) > 8 || Math.abs(d[1] - 208) > 8 || Math.abs(d[2] - 141) > 8) return false; } catch (e) { return false } }
  return true }"""
# Backup painted: MapLibre has loaded the style (TILE_VECTOR 'ready' only on load) and its canvas has a size.
OFM_PAINTED = """() => window.TILE_ACTIVE === 'openfreemap' && window.TILE_VECTOR === 'ready'
  && (() => { const c = document.querySelector('#map .leaflet-gl-layer canvas'); return !!c && c.width > 0 && c.height > 0 })()"""
STATE = """() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER || null, v: window.TILE_VECTOR || null, stats: window.TILE_STATS || null,
  zoom: map.getZoom(), max: map.getMaxZoom(), sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
  imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length})"""


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class LocateKeepsTheMapPainted(unittest.TestCase):
    def _run(self, spot, button, sw, mode):
        """mode: 'ok' (OSM fine), 'refuse' (OSM 429s from the press on: backup forced), 'refuse-badstyle' (and the
        backup's style is not JSON, like a blocked or broken response: must come back to OSM, not stay grey)."""
        from playwright.sync_api import sync_playwright
        import mimetypes
        lat, lng = SPOTS[spot]
        st = {'refuse': False, 'osm': 0, 'osm_urls': []}
        with sync_playwright() as p:
            iphone = dict(p.devices['iPhone 13']); iphone.pop('default_browser_type', None)
            b = p.webkit.launch()
            c = b.new_context(**iphone, service_workers='allow' if sw else 'block', geolocation={'latitude': lat, 'longitude': lng},
                              permissions=['geolocation'])

            def local(route):
                path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
                f = os.path.join(R, path.lstrip('/'))
                f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
                if not os.path.isfile(f):
                    return route.fulfill(status=404, body='')
                body = open(f, 'rb').read()
                if path == '/sw.js':
                    body = SW_STUB + body
                route.fulfill(status=200, body=body, headers={
                    'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})

            def osm(route):
                st['osm'] += 1; st['osm_urls'].append(route.request.url)
                if st['refuse']:
                    return route.fulfill(status=429, body='rate limited', headers={'access-control-allow-origin': '*'})
                route.fulfill(status=200, content_type='image/png', body=TILE, headers={
                    'access-control-allow-origin': '*', 'cache-control': 'public, max-age=86400', 'x-helpmap-tile': 'stub'})

            def ofm(route):
                if '/styles/' in route.request.url:
                    if mode == 'refuse-badstyle':
                        st['refuse'] = False  # OSM recovers; the broken backup must hand the map back to it
                        st['recover'] = True
                        return route.fulfill(status=200, content_type='image/png', body=TILE, headers={'access-control-allow-origin': '*'})
                    return route.fulfill(status=200, content_type='application/json', body=STYLE, headers={'access-control-allow-origin': '*'})
                route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
            c.route(BASE + '/**', local); c.route(BASE + '/', local)
            c.route('**://tile.openstreetmap.org/**', osm)
            c.route('**://*.openfreemap.org/**', ofm)
            pg = c.new_page()
            errors = []
            pg.on('pageerror', lambda e: errors.append(str(e)))
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
            if sw:
                self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller"), 'service worker never took control')
            self.assertTrue(until(pg, OSM_PAINTED), pg.evaluate(STATE))
            before = len(st['osm_urls'])
            if mode != 'ok':
                st['refuse'] = True
                if sw:
                    pg.evaluate("navigator.serviceWorker.controller.postMessage({hmStub: 'refuse'})")
            pg.click('#xnear' if button == 'near' else '#me')
            self.assertTrue(until(pg, "() => map.getZoom() >= 8"), pg.evaluate(STATE))
            pg.evaluate("document.getElementById('map').scrollIntoView()")
            want = OFM_PAINTED if mode == 'refuse' else OSM_PAINTED
            ok = until(pg, want, secs=30)
            os.makedirs(SHOTS, exist_ok=True)
            name = 'locate-%s-%s-%s-%s' % (spot, button, 'sw' if sw else 'nosw', mode)
            pg.screenshot(path=os.path.join(SHOTS, name + '-full.png'), full_page=True)
            pg.locator('#map').screenshot(path=os.path.join(SHOTS, name + '-map.png'))
            s = pg.evaluate(STATE)
            self.assertTrue(ok, s)
            self.assertLessEqual(s['zoom'], 19, s)
            if mode == 'refuse-badstyle':
                self.assertTrue((s['v'] or '').startswith('failed'), s)
                self.assertEqual(s['fo'].get('back'), 'osm', s)
            if mode == 'ok' and not sw:
                # One request per tile: the status fetch's bytes paint the image; no second download.
                after = st['osm_urls'][before:]
                self.assertTrue(after, s)
                self.assertEqual(len(after), len(set(after)), 'tiles fetched twice: %r' % after)
            self.assertEqual(errors, [])
            b.close()

    def test_find_nearest_littlehampton_sw_on(self): self._run('littlehampton', 'near', True, 'ok')
    def test_location_button_littlehampton_sw_on(self): self._run('littlehampton', 'me', True, 'ok')
    def test_find_nearest_manchester_sw_off(self): self._run('manchester', 'near', False, 'ok')
    def test_location_button_manchester_sw_off(self): self._run('manchester', 'me', False, 'ok')
    def test_find_nearest_429_after_load_backup_paints_sw_on(self): self._run('littlehampton', 'near', True, 'refuse')
    def test_location_button_429_after_load_backup_paints_sw_off(self): self._run('manchester', 'me', False, 'refuse')
    def test_backup_style_broken_comes_back_to_osm_not_grey(self): self._run('littlehampton', 'me', False, 'refuse-badstyle')


if __name__ == '__main__':
    unittest.main()
