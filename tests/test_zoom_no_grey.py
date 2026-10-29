"""Zooming out never shows grey (Dean, 29 Oct 2026), on Chromium and iPhone WebKit.

Dean's phone: the site opens on the whole-UK view, zooming in is fine, and as soon as he pinches out grey squares
appear around the square he is zooming away from. Main at c45116860 measured 81-94% of the map grey for 1-2 s on
every pinch-out of this journey. tiles.js now loads tiles during the pinch, paints tiles it has already shown from
memory with no request or fade, fills a zoom-out animation's wider view before it plays, and after a rest fetches
the tiles the next zoom-out needs.

The journey: open the UK view, pinch in level by level to a town (Littlehampton), then pinch out back to the UK.
Every animation frame of every pinch-out is sampled on a 48x30 grid over the visible map: a point no painted tile
covers is grey, and a point covered only by a tile from a lower zoom level (a stretched, blurry parent) is coarse.
Either fails the test. There is one tile layer, so nothing can be hidden under a backstop layer.

No real network: tests/netstub.py is the only way out of the browser, the service worker is on, tiles answer after
150 ms with the OpenStreetMap cache headers, and each z/x/y is a different image (the real UK map when
HELPMAP_OFFLINE_TILES points at the local tile server). Chromium also runs at a quarter of the CPU, like a phone.
"""
import json, os, struct, sys, time, unittest, urllib.request, zlib
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netstub

BASE = 'https://helpmap.uk'
TOWN = [50.8095, -0.5410]  # Littlehampton
TOWN_ZOOM = 13
PAUSE_MS = 1000
OSM_HEADERS = {'cache-control': 'max-age=14281, stale-while-revalidate=604800'}
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
IPHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
             'Version/18.0 Mobile/15E148 Safari/604.1')


def _engine_ok(name):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            getattr(p, name).launch().close()
        return True
    except Exception:
        return False


HAVE = {e: _engine_ok(e) for e in ('chromium', 'webkit')}
_TILES = {}


def _png(z, x, y):
    """A 256px tile that differs for every z/x/y: bands and a grid, about as costly to decode as a map tile."""
    seed = (z * 73856093) ^ (x * 19349663) ^ (y * 83492791)
    rows = []
    for j in range(256):
        row = bytearray(b'\x00')
        for i in range(256):
            k = (i // 16 + j // 16 + seed) & 7
            line = i % 64 == 0 or j % 64 == 0
            row += bytes((40, 40, 40)) if line else bytes((200 + k * 6, 196 + (seed >> k & 7) * 6, 186 + k * 4))
        rows.append(bytes(row))
    c = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + c(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0))
            + c(b'IDAT', zlib.compress(b''.join(rows), 6)) + c(b'IEND', b''))


def tile(path):
    if path not in _TILES:
        z, x, y = (int(v) for v in path.strip('/').replace('.png', '').split('/')[-3:])
        base = os.environ.get('HELPMAP_OFFLINE_TILES', '')
        body = None
        if base.startswith('http'):
            try:
                body = urllib.request.urlopen('%s/styles/bright/256/%d/%d/%d.png' % (base.rstrip('/'), z, x, y), timeout=30).read()
            except Exception:
                body = None
        _TILES[path] = body or _png(z, x, y)
    return _TILES[path]


SAMPLER = r"""() => {
  const mapEl = document.getElementById('map');
  const lay = () => { let l = null; map.eachLayer(x => { if (x._tiles && x.getTileUrl) l = x; }); return l; };
  const S = window.__zng = {frames: [], bad: []};
  function sample() {
    const r = mapEl.getBoundingClientRect(), L0 = lay();
    const x0 = Math.max(r.left, 0), y0 = Math.max(r.top, 0), x1 = Math.min(r.right, innerWidth), y1 = Math.min(r.bottom, innerHeight);
    if (!L0 || x1 - x0 < 20 || y1 - y0 < 20) return null;
    const tz = L0._tileZoom, rects = [];
    for (const k in L0._tiles) {
      const t = L0._tiles[k], img = t.el;
      if (!img.classList.contains('leaflet-tile-loaded') || !img.complete || !img.naturalWidth) continue;
      let op = 1, el = img;
      while (el && el !== mapEl) { const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none') { op = 0; break; } op *= parseFloat(cs.opacity); el = el.parentElement; }
      if (op < 0.5) continue;
      const b = img.getBoundingClientRect();
      rects.push([b.left - 0.5, b.top - 0.5, b.right + 0.5, b.bottom + 0.5, t.coords.z >= tz]);
    }
    const NX = 48, NY = 30; let grey = 0, coarse = 0;
    for (let i = 0; i < NX; i++) for (let j = 0; j < NY; j++) {
      const x = x0 + (i + 0.5) * (x1 - x0) / NX, y = y0 + (j + 0.5) * (y1 - y0) / NY;
      let hit = false, sharp = false;
      for (const q of rects) if (x >= q[0] && x <= q[2] && y >= q[1] && y <= q[3]) { hit = true; if (q[4]) { sharp = true; break; } }
      if (!hit) grey++; else if (!sharp) coarse++;
    }
    return {grey: grey / (NX * NY), coarse: coarse / (NX * NY), z: Math.round(map.getZoom() * 100) / 100, tz: tz,
            layers: mapEl.querySelectorAll('.leaflet-tile-pane .leaflet-layer').length};
  }
  window.__zngSample = sample;
  function tick() {
    const f = sample();
    if (f) {
      S.frames.push(f);
      if ((f.grey > 0 || f.coarse > 0) && S.bad.length < 5) {
        f.pending = [...mapEl.querySelectorAll('.leaflet-tile-pane img.leaflet-tile:not(.leaflet-tile-loaded)')]
          .slice(0, 6).map(i => (i.getAttribute('data-tile') || '').split('/').slice(-3).join('/'));
        S.bad.push(f);
      }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}"""

SETTLED = """() => { const s = window.__zngSample && window.__zngSample();
  return !!s && !map._animatingZoom && !(map.touchZoom && map.touchZoom._zooming) && s.grey === 0
    && !document.querySelector('#map .leaflet-tile-pane img.leaflet-tile:not(.leaflet-tile-loaded)'); }"""

# Two fingers on the map, as the touch events Leaflet reads. WebKit, like iOS, has no Touch constructor.
PINCH_JS = r"""async ([a, b, steps, ms]) => {
  const el = document.getElementById('map'), r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const pts = d => [[1, cx - d], [2, cx + d]].map(([id, x]) => ({identifier: id, target: el, clientX: x, clientY: cy,
    pageX: x + scrollX, pageY: cy + scrollY, screenX: x, screenY: cy, radiusX: 1, radiusY: 1, force: 1}));
  const fire = (type, touches, changed) => {
    const e = new Event(type, {bubbles: true, cancelable: true});
    for (const [k, v] of [['touches', touches], ['targetTouches', touches], ['changedTouches', changed]]) Object.defineProperty(e, k, {value: v});
    el.dispatchEvent(e);
  };
  fire('touchstart', pts(a), pts(a));
  let d = a;
  for (let i = 1; i <= steps; i++) { await new Promise(f => setTimeout(f, ms)); d = a + (b - a) * i / steps; fire('touchmove', pts(d), pts(d)); }
  fire('touchend', [], pts(d));
}"""


def until(pg, js, secs=30):
    end = time.time() + secs
    while time.time() < end:
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(100)
    return False


def settle(pg, secs=40):
    """Settled for five checks in a row: no zoom running, no tile waiting, nothing grey."""
    ok, end = 0, time.time() + secs
    while time.time() < end:
        ok = ok + 1 if pg.evaluate(SETTLED) else 0
        if ok >= 5:
            return True
        pg.wait_for_timeout(100)
    return False


class ZoomOutNoGrey(unittest.TestCase):
    def browser(self, p, engine):
        if engine == 'chromium':
            # Chromium uses neither the service worker nor the HTTP cache on an origin with a certificate error.
            b = p.chromium.launch(args=['--ignore-certificate-errors'])
            ctx = dict(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True, user_agent=IPHONE_UA)
        else:
            b = p.webkit.launch()
            ctx = dict(p.devices['iPhone 13'])
            ctx.pop('default_browser_type', None)
        return b, ctx

    def pinch(self, pg, c, engine, a, b):
        if engine == 'chromium':
            cdp = c.new_cdp_session(pg)
            cx, cy = pg.evaluate("() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
            pts = lambda d: [{'x': cx - d, 'y': cy, 'id': 1}, {'x': cx + d, 'y': cy, 'id': 2}]
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': pts(a)})
            for i in range(1, 25):
                time.sleep(0.03)
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': pts(a + (b - a) * i / 24)})
            cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            cdp.detach()
        else:
            pg.evaluate(PINCH_JS, [a, b, 24, 30])

    def open(self, p, net, engine, sw=True):
        b, ctx = self.browser(p, engine)
        c = b.new_context(**ctx, service_workers='allow' if sw else 'block', **net.context_options())
        pg = c.new_page()
        if engine == 'chromium':
            c.new_cdp_session(pg).send('Emulation.setCPUThrottlingRate', {'rate': 4})
        pg.goto(BASE + '/?nocount', wait_until='domcontentloaded')
        return b, c, pg

    def journey(self, engine):
        from playwright.sync_api import sync_playwright
        with netstub.Stub(OFM_STYLE, tile, tile_latency=0.15, tile_headers=OSM_HEADERS) as net, sync_playwright() as p:
            b, c, pg = self.open(p, net, engine)
            try:
                self.assertTrue(until(pg, "() => typeof map !== 'undefined' && !!document.querySelector('#map .leaflet-tile-loaded')", 60), 'map never painted')
                self.assertTrue(until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 30), 'service worker never took control')
                pg.evaluate("() => { const m = document.getElementById('map'); window.scrollTo(0, m.getBoundingClientRect().top + scrollY - (innerHeight - m.offsetHeight) / 2); }")
                pg.evaluate(SAMPLER)
                self.assertTrue(settle(pg), 'the UK view never finished loading')
                z0 = pg.evaluate('() => map.getZoom()')
                self.assertLessEqual(z0, 7, 'the site no longer opens on the whole-UK view')
                pg.evaluate("() => map.setView(%s, %d, {animate: false})" % (json.dumps(TOWN), round(z0)))
                self.assertTrue(settle(pg))
                pg.wait_for_timeout(PAUSE_MS)
                for _ in range(16):
                    if pg.evaluate('() => map.getZoom()') >= TOWN_ZOOM - 0.01:
                        break
                    self.pinch(pg, c, engine, 60, 120)
                    self.assertTrue(settle(pg), 'zoom-in never finished loading')
                    pg.wait_for_timeout(PAUSE_MS)
                self.assertGreaterEqual(pg.evaluate('() => map.getZoom()'), TOWN_ZOOM - 0.01, 'the pinches never reached the town')
                report, failed = [], False
                for _ in range(12):
                    if pg.evaluate('() => map.getZoom()') <= z0 + 0.01:
                        break
                    n0 = len(net.tile_paths)
                    pg.evaluate("() => { window.__zng.frames = []; window.__zng.bad = []; }")
                    self.pinch(pg, c, engine, 160, 30)
                    done = settle(pg)
                    st = pg.evaluate("() => window.__zng")
                    fr = st['frames']
                    grey = [f for f in fr if f['grey'] > 0]
                    coarse = [f for f in fr if f['coarse'] > 0]
                    layers = max(f['layers'] for f in fr) if fr else 0
                    row = {'to': pg.evaluate('() => map.getZoom()'), 'frames': len(fr), 'grey_frames': len(grey),
                           'grey_max_pct': round(max([f['grey'] for f in grey] or [0]) * 100, 1), 'coarse_frames': len(coarse),
                           'tile_layers': layers, 'tile_requests': len(net.tile_paths) - n0, 'settled': done, 'first_bad': st['bad'][:2]}
                    report.append(row)
                    failed = failed or bool(grey or coarse) or layers != 1 or not done or not fr
                    pg.wait_for_timeout(PAUSE_MS)
                self.assertLessEqual(pg.evaluate('() => map.getZoom()'), z0 + 0.01, ('the pinches never got back to the UK view', report))
                self.assertGreaterEqual(len(report), 3, report)
                self.assertFalse(failed, json.dumps(report, indent=1))
                self.assertTrue(pg.evaluate("() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)"))
                self.assertEqual(net.refused, [], 'a request left the stub network')
            finally:
                b.close()

    def lookahead_stops_on_backup(self, engine):
        """OpenStreetMap refused: once the backup map takes over, no more OSM tile is asked for, look-ahead included."""
        from playwright.sync_api import sync_playwright
        with netstub.Stub(OFM_STYLE, tile, osm=False) as net, sync_playwright() as p:
            b, c, pg = self.open(p, net, engine)
            try:
                self.assertTrue(until(pg, "() => window.TILE_ACTIVE === 'openfreemap'", 60),
                                pg.evaluate("() => ({active: window.TILE_ACTIVE || null, fo: window.TILE_FAILOVER || null})"))
                before = (net.osm_refused(), pg.evaluate("() => (window.TILE_STATS || {}).ahead || 0"))
                pg.wait_for_timeout(4000)
                after = (net.osm_refused(), pg.evaluate("() => (window.TILE_STATS || {}).ahead || 0"))
                self.assertEqual(after, before, 'OpenStreetMap was still asked for after the backup took over (refused, look-ahead)')
                self.assertEqual(net.served['osm'], 0)
            finally:
                b.close()

    @unittest.skipUnless(HAVE['chromium'], 'needs playwright chromium')
    def test_chromium_open_uk_zoom_in_pinch_out_never_grey(self):
        self.journey('chromium')

    @unittest.skipUnless(HAVE['webkit'], 'needs playwright webkit')
    def test_webkit_open_uk_zoom_in_pinch_out_never_grey(self):
        self.journey('webkit')

    @unittest.skipUnless(HAVE['chromium'], 'needs playwright chromium')
    def test_chromium_lookahead_stops_when_backup_map_takes_over(self):
        self.lookahead_stops_on_backup('chromium')

    @unittest.skipUnless(HAVE['webkit'], 'needs playwright webkit')
    def test_webkit_lookahead_stops_when_backup_map_takes_over(self):
        self.lookahead_stops_on_backup('webkit')


if __name__ == '__main__':
    unittest.main()
