"""iPhone map fix (27 Oct 2026, replaces PR 172).

Real-world case on Dean's iPhone: the unversioned 'fyfb-tiles' cache still held OPAQUE OpenStreetMap
tiles from the 21 Oct build (no crossOrigin then). The tiles.js status probe is a CORS fetch; a service
worker may not answer a CORS request with an opaque response (Fetch spec), WebKit throws "Response served
by service worker is opaque", that counted as a tile failure and the map switched to OpenFreeMap.

These checks run Playwright WebKit with the iPhone 13 profile, the checkout served as https://helpmap.uk.
Tile hosts are stubbed; nothing here contacts a public tile server.
"""
import os, subprocess, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone_webkit import DEVICES, iphone_context
from standin_net import Proxy, StandIn
BASE = 'https://helpmap.uk'
OFM = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
       '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
       '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}}]}')
URLS = "(() => { const u = []; for (let x = 13; x <= 17; x++) for (let y = 8; y <= 12; y++) u.push('https://tile.openstreetmap.org/5/' + x + '/' + y + '.png'); return u; })()"


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


def old_sw(rev='e3982436c'):
    """sw.js from an older build. e3982436c is fyfb-v90 (live before this fix); 5c31f005c is fyfb-v89."""
    return subprocess.check_output(['git', 'show', rev + ':sw.js'], cwd=R)


PAINTED = """() => window.TILE_ACTIVE==='osm'
  && document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4
  && [...document.querySelectorAll('#map img.leaflet-tile-loaded')].every(i => i.src.includes('tile.openstreetmap.org') && i.naturalWidth > 0)
  && !window.maplibregl && !window.TILE_FAILOVER"""
STATE = "() => ({active: window.TILE_ACTIVE, fo: window.TILE_FAILOVER||null, v: window.TILE_VECTOR||null, stats: window.TILE_STATS||null, lib: !!window.maplibregl, imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length})"


class Source(unittest.TestCase):
    def test_source_carries_the_fix(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        css = open(os.path.join(R, 'header.css'), encoding='utf-8').read()
        self.assertNotIn('img.crossOrigin', tiles)
        self.assertNotIn('crossOrigin: true', tiles)
        self.assertIn("'probe-opaque'", tiles)
        self.assertIn('debugReadout(map)', tiles)
        self.assertIn('retry', tiles)
        self.assertIn("hit.type!=='opaque'", sw)
        self.assertIn("T='fyfb-tiles2'", sw)
        self.assertIn('x!==C&&x!==T', sw)  # activate deletes every other cache, so the old fyfb-tiles goes
        self.assertNotIn("r.type==='opaque'){c.put", sw)
        self.assertIn('#map .leaflet-gl-layer,#map .leaflet-gl-layer *{pointer-events:none!important}', home)
        self.assertIn('pointer-events:none!important', css)
        self.assertIn('tiles.js?v=h9d4d60e584e4', home)
        self.assertIn('tiles.js?v=h9d4d60e584e4', sw)


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class IPhone(unittest.TestCase):
    def _ctx(self, p, sw_body=None, init=None, device='iPhone 13', decide=None, missing=()):
        """iPhone WebKit, service worker on. Tiles and the OpenFreeMap style come from the local stand-in, not route()."""
        stand = StandIn(R, style=OFM)
        stand.sw_body = sw_body
        stand.missing = missing
        if decide is not None:
            stand.decide = decide
        proxy = Proxy(stand)
        b = p.webkit.launch()
        c = iphone_context(p, b, device, proxy=proxy)
        if init:
            c.add_init_script(init)
        return b, c, stand, proxy

    def test_phone_with_old_opaque_tile_cache_stays_on_openstreetmap(self):
        """Old build (v90) fills 'fyfb-tiles' with opaque tiles; the new worker takes over, deletes that store, and the
        map paints OpenStreetMap tiles with no switch to OpenFreeMap. iPhone 13 and iPhone SE, service worker on."""
        for device in DEVICES:
            self._old_cache('e3982436c', device)

    def test_phone_from_a_v89_opaque_tile_cache_stays_on_openstreetmap(self):
        for device in DEVICES:
            self._old_cache('5c31f005c', device)

    def _old_cache(self, rev, device='iPhone 13'):
        from playwright.sync_api import sync_playwright
        proxy = None
        try:
            with sync_playwright() as p:
                b, c, stand, proxy = self._ctx(p, sw_body=old_sw(rev), device=device)
                pg = c.new_page()
                pg.goto(BASE + '/?nocount', wait_until='load')
                self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller"), 'old worker did not take control')
                seeded = pg.evaluate("""async () => {
                  const urls = %s;
                  await Promise.all(urls.map(u => fetch(u, {mode: 'no-cors'}).catch(() => null)));
                  const c = await caches.open('fyfb-tiles'); let opaque = 0;
                  for (let n = 0; n < 40 && opaque < urls.length; n++) { opaque = 0;
                    for (const u of urls) { const h = await c.match(u); if (h && h.type === 'opaque') opaque++; }
                    if (opaque < urls.length) await new Promise(r => setTimeout(r, 50)); }
                  return {opaque, want: urls.length};
                }""" % URLS)
                self.assertEqual(seeded['opaque'], seeded['want'], seeded)
                # Proof the bug exists under the old worker: a CORS probe of an opaque cached tile throws.
                threw = pg.evaluate("async () => { try { await fetch('https://tile.openstreetmap.org/5/15/10.png'); return false } catch (e) { return true } }")
                self.assertTrue(threw, 'old worker did not reproduce the opaque failure')
                stand.sw_body = None  # the new sw.js from this checkout
                pg.goto(BASE + '/?nocount', wait_until='load')  # layers.js registers sw.js?v=57, a new worker
                self.assertTrue(until(pg, "async () => !(await caches.keys()).includes('fyfb-tiles') && (await caches.keys()).includes('fyfb-v91')", 30),
                                pg.evaluate('async () => await caches.keys()'))
                pg.reload(wait_until='load')
                self.assertTrue(until(pg, PAINTED), pg.evaluate(STATE))
                pg.wait_for_timeout(1500)
                st = pg.evaluate(STATE)
                self.assertEqual(st['active'], 'osm', st)
                self.assertIsNone(st['fo'], st)
                self.assertFalse(st['lib'], st)
                b.close()
        finally:
            if proxy:
                proxy.stop()

    def test_opaque_tiles_in_the_live_cache_are_refetched_not_served_to_the_probe(self):
        """Worker-cache full of opaque OSM tiles (the real-world case) in the current store: no switch, tiles paint,
        and each opaque entry is replaced by a readable copy. iPhone 13 and iPhone SE, service worker on."""
        for device in DEVICES:
            self._live_opaque(device)

    def _live_opaque(self, device):
        from playwright.sync_api import sync_playwright
        proxy = None
        try:
            with sync_playwright() as p:
                b, c, stand, proxy = self._ctx(p, device=device)
                pg = c.new_page()
                pg.goto(BASE + '/?nocount', wait_until='load')
                self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller"), 'worker did not take control')
                seeded = pg.evaluate("""async () => {
                  map._hmTileStop();
                  await caches.delete('fyfb-tiles2');
                  const urls = %s, c = await caches.open('fyfb-tiles2');
                  for (const u of urls) await c.put(u, await fetch(new Request(u, {mode: 'no-cors'}), {cache: 'no-store'}));
                  let opaque = 0; for (const u of urls) { const h = await c.match(u); if (h && h.type === 'opaque') opaque++; }
                  const thrown = await fetch(urls[0]).then(r => r.ok, () => 'threw');
                  return {opaque, want: urls.length, probe: thrown};
                }""" % URLS)
                self.assertEqual(seeded['opaque'], seeded['want'], seeded)
                self.assertIs(seeded['probe'], True, seeded)  # the worker went to the network, not the opaque copy
                pg.evaluate("() => { delete window.TILE_FAILOVER; addTiles(map); map.setView([53.48, -2.24], 5); }")
                self.assertTrue(until(pg, PAINTED), pg.evaluate(STATE))
                pg.wait_for_timeout(1500)
                st = pg.evaluate(STATE)
                self.assertEqual(st['active'], 'osm', st)
                self.assertIsNone(st['fo'], st)
                self.assertFalse(st['lib'], st)
                b.close()
        finally:
            if proxy:
                proxy.stop()

    def _ofm_broken(self, init=None, lib_404=False, device='iPhone 13'):
        from playwright.sync_api import sync_playwright
        seen = {'osm': 0}
        proxy = None
        try:
            with sync_playwright() as p:
                stand_box = {}

                def decide(host, path):
                    stand = stand_box['stand']
                    if host == 'tile.openstreetmap.org' or host.endswith('.tile.openstreetmap.org'):
                        seen['osm'] += 1
                        if seen['osm'] <= 3:  # 3 refusals: a real failure, switches to the backup
                            return stand.png(403)
                        return stand.png(200, stub=True)
                    if 'openfreemap.org' in host:
                        low = path.lower()
                        if '/styles/' in low or low.endswith('.json') or 'tilejson' in low:
                            return stand.json_style()
                        return stand.empty(404)
                    if host in ('helpmap.uk', 'www.helpmap.uk'):
                        return stand.site_file(path)
                    stand.other.append(host + path[:80])
                    return stand.empty(403)

                missing = ('/vendor/maplibre-gl-csp.js',) if lib_404 else ()
                b, c, stand, proxy = self._ctx(p, init=init, device=device, decide=decide, missing=missing)
                stand_box['stand'] = stand
                pg = c.new_page()
                pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
                self.assertTrue(until(pg, "() => !!window.TILE_FAILOVER && /^failed/.test(window.TILE_VECTOR||'')"), pg.evaluate(STATE))
                self.assertTrue(until(pg, """() => window.TILE_ACTIVE==='osm' && window.TILE_FAILOVER.back==='osm'
                  && document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4"""), pg.evaluate(STATE))
                pg.wait_for_timeout(2500)  # no flip-flop back to OpenFreeMap
                st = pg.evaluate(STATE)
                self.assertEqual(st['active'], 'osm', st)
                self.assertFalse(pg.evaluate("() => !!document.querySelector('#map .leaflet-gl-layer')"))
                self.assertIn('back to osm', pg.evaluate("() => document.getElementById('tiles-debug').innerText"))
                b.close()
        finally:
            if proxy:
                proxy.stop()

    def test_openfreemap_library_failing_to_load_falls_back_to_openstreetmap(self):
        """MapLibre script is HTTP 404 from the local server. Service worker on. iPhone 13 and iPhone SE."""
        for device in DEVICES:
            self._ofm_broken(lib_404=True, device=device)

    def test_no_webgl_falls_back_to_openstreetmap_not_blank(self):
        """No WebGL. OSM refusals are HTTP 403 from the local server, not route(). Service worker on."""
        for device in DEVICES:
            self._ofm_broken(device=device, init="""(() => { const g = HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); }; })()""")


if __name__ == '__main__':
    unittest.main()
