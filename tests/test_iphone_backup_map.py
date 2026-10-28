"""iPhone WebKit: the OpenFreeMap backup really is forced, and it paints, with the service worker on and off.

27 Oct 2026 live check of main 4ad81532e:
  1. The 'backup map on' check blocked OpenStreetMap with context.route(). Playwright does not route requests
     made by a service worker in WebKit, so sw.js fetched OSM tiles past the block: OSM loaded in 3 of 5
     iPhone 13 runs and the backup was never forced. Here the block is at the network layer (tests/netstub.py,
     a local proxy every browser request goes through), so it holds for the page and the service worker alike.
  2. With the service worker off and OSM blocked, the backup came up grey after
     'SyntaxError: The string did not match the expected pattern'. That error is WebKit's Response.json() on a
     non-JSON body: the OpenFreeMap style request (https://tiles.openfreemap.org/styles/positron) was answered
     with a PNG by a test harness tile stub that covers every tile host, so MapLibre could not parse the style.
     These cases check the backup gets its JSON style, paints, and never logs that error.

Matrix: iPhone 13 and iPhone SE x backup off/on x service worker on/off. No real network.
HELPMAP_WK_DEVICES / HELPMAP_WK_BACKUP / HELPMAP_WK_SW narrow the matrix for a quick local run.
"""
import os, struct, sys, unittest, zlib
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netstub

BASE = 'https://helpmap.uk'
TILE_PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
# Same stand-in style as tests/test_tile_fallback.py and tests/test_iphone_responsive.py (rule 23: no real vector tiles).
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
LAND = (0xa8, 0xd0, 0x8d)  # the stand-in style's land fill: only MapLibre drawing the style puts this colour on screen
STATE = """() => ({active: window.TILE_ACTIVE || 'osm', fo: window.TILE_FAILOVER || null, vector: window.TILE_VECTOR || null,
  canvas: !!document.querySelector('#map canvas.maplibregl-canvas'), lib: !!window.maplibregl,
  imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length,
  sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller)})"""


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


def pixel(png):
    """RGB of a 1x1 PNG screenshot. With one pixel every PNG filter predicts 0, so the raw bytes are the colour."""
    i, idat, ct = 8, b'', 2
    while i < len(png):
        n, t = struct.unpack('>I4s', png[i:i + 8])
        if t == b'IHDR':
            ct = png[i + 17]
        if t == b'IDAT':
            idat += png[i + 8:i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(idat)
    assert ct in (2, 6), ct
    return tuple(raw[1:4])


def near(c, want, tol=14):
    return all(abs(a - b) <= tol for a, b in zip(c, want))


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class IPhoneBackupMap(unittest.TestCase):
    def case(self, device, backup, sw):
        from playwright.sync_api import sync_playwright
        errs = []
        with netstub.Stub(OFM_STYLE, TILE_PNG, osm=not backup) as net, sync_playwright() as p:
            b = p.webkit.launch()
            try:
                dev = dict(p.devices[device])
                dev.pop('default_browser_type', None)
                c = b.new_context(**dev, service_workers='allow' if sw else 'block', **net.context_options())
                pg = c.new_page()
                pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
                pg.on('console', lambda m: errs.append(m.text[:200]) if m.type == 'error' else None)
                pg.goto(BASE + '/?nocount&tiles=debug', wait_until='domcontentloaded')
                if sw:
                    self.assertTrue(until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 30),
                                    'service worker never took control')
                    pg.reload(wait_until='domcontentloaded')  # second load: every tile request goes through sw.js
                self.assertTrue(until(pg, "() => !!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))", 40), 'map never built')
                if not backup:
                    self.assertTrue(until(pg, "() => window.TILE_ACTIVE !== 'openfreemap' && document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4", 40),
                                    pg.evaluate(STATE))
                    pg.wait_for_timeout(1500)
                    st = pg.evaluate(STATE)
                    self.assertEqual(st['active'], 'osm', st)
                    self.assertIsNone(st['fo'], st)
                    self.assertFalse(st['lib'], st)
                    self.assertGreater(net.served['osm'], 0)
                else:
                    ok = until(pg, "() => window.TILE_ACTIVE === 'openfreemap' && window.TILE_VECTOR === 'ready' && !!document.querySelector('#map canvas.maplibregl-canvas')", 60)
                    self.assertTrue(ok, (pg.evaluate(STATE), errs[:5]))
                    # The block held for everyone, service worker included: no OSM tile was ever served, and OSM was refused.
                    self.assertEqual(net.served['osm'], 0, 'an OpenStreetMap tile got past the block')
                    self.assertGreater(net.osm_refused(), 0, 'OpenStreetMap was never even asked for')
                    # It paints: the style's land colour is on screen, not the grey empty map.
                    painted = []
                    pg.locator('#map').scroll_into_view_if_needed()
                    for _ in range(40):
                        box = pg.locator('#map').bounding_box()
                        painted = []
                        for fx in (0.15, 0.35, 0.5, 0.65, 0.85):
                            for fy in (0.15, 0.35, 0.5, 0.65, 0.85):
                                if box['y'] + box['height'] * fy >= pg.viewport_size['height'] - 1:
                                    continue
                                px = pixel(pg.screenshot(clip={'x': box['x'] + box['width'] * fx, 'y': box['y'] + box['height'] * fy, 'width': 1, 'height': 1}))
                                if near(px, LAND):
                                    painted.append(px)
                        if len(painted) >= 5:
                            break
                        pg.wait_for_timeout(250)
                    self.assertGreaterEqual(len(painted), 5, ('backup map did not paint', pg.evaluate(STATE)))
                    self.assertGreater(net.served['ofm'], 0, 'the OpenFreeMap style was never fetched')
                    self.assertEqual(net.served['osm'], 0, 'an OpenStreetMap tile got past the block')
                    st = pg.evaluate(STATE)
                    self.assertEqual(st['active'], 'openfreemap', st)
                if sw:
                    self.assertTrue(pg.evaluate(STATE)['sw'], 'service worker was not in control during the check')
                pattern = [e for e in errs if 'expected pattern' in e]
                self.assertEqual(pattern, [], pattern)
            finally:
                b.close()


def _want(env, all_):
    v = os.environ.get(env)
    return [x for x in all_ if not v or x in v.split(',')]


for _dev in _want('HELPMAP_WK_DEVICES', ['iPhone 13', 'iPhone SE']):
    for _bk in _want('HELPMAP_WK_BACKUP', ['off', 'on']):
        for _sw in _want('HELPMAP_WK_SW', ['on', 'off']):
            def _t(self, d=_dev, bk=_bk, s=_sw):
                self.case(d, bk == 'on', s == 'on')
            _t.__doc__ = '%s, backup map %s, service worker %s' % (_dev, _bk, _sw)
            setattr(IPhoneBackupMap, 'test_%s_backup_%s_sw_%s' % (_dev.replace(' ', '').lower(), _bk, _sw), _t)


if __name__ == '__main__':
    unittest.main()
