"""Angle B: OSM 429, then Locate or Find nearest, must not leave a grey OpenFreeMap.

Confirmed on main (27 Oct 2026), service worker off, iPhone 13 and iPhone SE: OSM answers 429,
the map switches to OpenFreeMap, TILE_VECTOR is set to 'ready' as the layer is added, and no
vector tile is requested. The canvas stays grey. WebKit's 'The string did not match the expected
pattern' never reached fail(), because nothing listened for MapLibre's error and nothing noticed
that load/idle had not painted.

These checks use Playwright WebKit with the service worker blocked, this checkout served as
https://helpmap.uk. Tile hosts are stubbed. A painted OpenStreetMap tile is the 1×1 stand-in
(RGB 186,214,156), proved by sampling the map's drawn pixels, not by counting <img> tags.
A page load is a main-frame navigation; recovery must not reload. Nothing here contacts a public
tile server.

  repro  — the map paints, then OSM 429s and Locate (iPhone 13) or Find nearest (iPhone SE) runs.
           The style is left unanswered, so the backup starts, requests 0 vector tiles and draws
           nothing. The watchdog returns to OpenStreetMap once and the stand-in paints.
  fatal  — the same gesture, but the style answers 500. That is a style failure, so fail()
           returns to OpenStreetMap without waiting out the watchdog.
  assets — a missing glyph, sprite and vector tile must not fail() the backup. The stand-in
           style paints and is still OpenFreeMap after the watchdog has had time to fire.
"""
import os, struct, subprocess, sys, time, unittest, zlib
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = 'https://helpmap.uk'
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
TILE = (186, 214, 156)   # the 1×1 stand-in, scripts/tile_placeholder.png
LAND = (168, 208, 141)   # the stub style's land fill
OFM = ('{"version":8,"glyphs":"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",'
       '"sprite":"https://tiles.openfreemap.org/sprites/positron",'
       '"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
       '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}},'
       '"roads":{"type":"vector","tiles":["https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf"],"maxzoom":14}},'
       '"layers":[{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
       '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}},'
       '{"id":"roads","type":"line","source":"roads","source-layer":"road","paint":{"line-color":"#333","line-width":1}},'
       '{"id":"label","type":"symbol","source":"uk","layout":{"text-field":"Bank","text-font":["Noto Sans Regular"],"text-size":14}}]}')
# Runs on every document, including one the fallback must not create. sessionStorage survives a reload.
BOOT = """(() => {
  try { sessionStorage.setItem('hmLoads', String((+sessionStorage.getItem('hmLoads') || 0) + 1)); } catch (e) {}
  var geo = navigator.geolocation;
  if (geo) geo.getCurrentPosition = function (ok) {
    ok({coords: {latitude: 53.48, longitude: -2.24, accuracy: 20}});
  };
  window.__hmHist = [];
  setInterval(function () {
    var c = false;
    try { c = !!document.querySelector('#map .leaflet-gl-layer canvas'); } catch (e) {}
    window.__hmHist.push({t: performance.now(), a: window.TILE_ACTIVE || '', v: window.TILE_VECTOR || '', c: c});
    if (window.__hmHist.length > 800) window.__hmHist.shift();
  }, 40);
})()"""
STATE = """() => ({
  a: window.TILE_ACTIVE,
  v: window.TILE_VECTOR || '',
  canvas: !!document.querySelector('#map .leaflet-gl-layer canvas'),
  loads: +sessionStorage.getItem('hmLoads') || 0,
  back: (window.TILE_FAILOVER || {}).back || null
})"""
LIMIT = {'repro': 55, 'fatal': 40, 'assets': 45}
CHILD = len(sys.argv) == 3 and sys.argv[1] in LIMIT


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = True if CHILD else have_webkit()


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def drawn_pixels(data, step=6):
    """Sample a PNG of the map. Counts stand-in green and stub-land green among drawn pixels."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError('screenshot is not a png (%s bytes)' % len(data))
    i, w, h, color, depth, idat = 8, None, None, None, None, b''
    while i < len(data):
        n = struct.unpack('>I', data[i:i + 4])[0]
        typ, chunk = data[i + 4:i + 8], data[i + 8:i + 8 + n]
        if typ == b'IHDR':
            w, h, depth, color = struct.unpack('>IIBB', chunk[:10])
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
        i += 12 + n
    if depth != 8 or color not in (2, 6):
        raise AssertionError('unexpected png %s bit color %s' % (depth, color))
    bpp = (3 if color == 2 else 4)
    raw, stride = zlib.decompress(idat), w * bpp
    pos, prev, rows = 0, bytearray(stride), []
    for _y in range(h):
        f, row = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for x in range(stride):
            left = row[x - bpp] if x >= bpp else 0
            up, ul = prev[x], (prev[x - bpp] if x >= bpp else 0)
            if f == 1:
                row[x] = (row[x] + left) & 255
            elif f == 2:
                row[x] = (row[x] + up) & 255
            elif f == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 255
            elif f == 4:
                row[x] = (row[x] + _paeth(left, up, ul)) & 255
            elif f != 0:
                raise AssertionError('png filter %s' % f)
        rows.append(row)
        prev = row
    tile = land = n = 0
    for y in range(0, h, step):
        row = rows[y]
        for x in range(0, w, step):
            o = x * bpp
            r, g, b = row[o], row[o + 1], row[o + 2]
            n += 1
            if abs(r - TILE[0]) < 14 and abs(g - TILE[1]) < 14 and abs(b - TILE[2]) < 14:
                tile += 1
            if abs(r - LAND[0]) < 14 and abs(g - LAND[1]) < 14 and abs(b - LAND[2]) < 14:
                land += 1
    return {'n': n, 'tile': tile, 'land': land, 'w': w, 'h': h,
            'tileFrac': tile / n if n else 0, 'landFrac': land / n if n else 0}


class Source(unittest.TestCase):
    def test_only_a_fatal_error_or_the_watchdog_falls_back_once(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertIn("gl.on('error'", tiles)
        self.assertIn("gl.on('load'", tiles)
        self.assertIn("gl.on('idle'", tiles)
        self.assertIn('window.TILE_VECTOR_WATCH_MS = 8000', tiles)
        self.assertIn("new Error('no tiles')", tiles)
        self.assertIn("new Error('webgl unsupported')", tiles)
        self.assertIn("window.TILE_VECTOR = 'loading'", tiles)
        self.assertIn("window.TILE_VECTOR = 'ready'", tiles)
        self.assertNotRegex(tiles, r"addTo\(map\);\s*window\.TILE_VECTOR = 'ready'")
        self.assertIn('vectorFailed = true', tiles)
        self.assertIn('function fatalVectorError', tiles)
        self.assertIn('function claim()', tiles)
        self.assertEqual(tiles.count('settled = true'), 1)
        self.assertIn('ev.tile', tiles)
        self.assertIn('ev.sourceId', tiles)
        self.assertIn('ev.style', tiles)
        self.assertRegex(tiles, r'glyph\|sprite\|fontstack')
        self.assertNotRegex(tiles, r'sawPaint && sawIdle\) return')


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class IPhoneVectorRecover(unittest.TestCase):
    def _guarded(self, kind, device):
        pr = subprocess.Popen(
            [sys.executable, '-u', os.path.abspath(__file__), kind, device],
            cwd=R, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = pr.communicate(timeout=LIMIT[kind])
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9)
            out, err = pr.communicate()
            self.fail('%s %s froze, no answer within %ds\n%s' % (kind, device, LIMIT[kind], (out or '')[-800:]))
        print((out or '')[-600:])
        self.assertEqual(pr.returncode, 0, '%s %s failed:\n%s%s' % (kind, device, out[-2000:], err[-2000:]))

    def test_osm_429_then_locate_or_find_nearest_recovers_and_paints(self):
        self._guarded('repro', 'iPhone 13')
        self._guarded('repro', 'iPhone SE')

    def test_fatal_style_error_returns_without_the_watchdog(self):
        self._guarded('fatal', 'iPhone 13')
        self._guarded('fatal', 'iPhone SE')

    def test_missing_glyph_or_tile_does_not_drop_the_backup(self):
        self._guarded('assets', 'iPhone 13')
        self._guarded('assets', 'iPhone SE')


def _local(route):
    import mimetypes
    path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
    f = os.path.join(R, path.lstrip('/'))
    f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
    if not os.path.isfile(f):
        return route.fulfill(status=404, body='')
    route.fulfill(status=200, body=open(f, 'rb').read(), headers={
        'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})


def _shot(pg):
    return drawn_pixels(pg.locator('#map').screenshot(type='png'))


def run_case(kind, device):
    from playwright.sync_api import sync_playwright
    phase = {'arm': kind == 'assets', 'ofm': False, 'again': False, 'hung': [],
             'osm': 0, 'denied': 0, 'ok_urls': set(), 'style': 0, 'vector': 0,
             'glyph': 0, 'sprite': 0, 'tileErr': 0}
    outside, navs = [], []

    def osm(route):
        phase['osm'] += 1
        url = route.request.url.split('?')[0]
        fresh = url not in phase['ok_urls']
        if not phase['arm']:
            phase['ok_urls'].add(url)
        deny = phase['again'] or (phase['arm'] and fresh and not phase['ofm'])
        if deny:
            phase['denied'] += 1
            status = 429
        else:
            status = 200
        route.fulfill(status=status, content_type='image/png', body=PNG, headers={
            'access-control-allow-origin': '*', 'cache-control': 'no-store'})

    def ofm(route):
        phase['ofm'] = True
        url = route.request.url
        if '/styles/positron' in url:
            phase['style'] += 1
            if kind == 'repro':
                phase['hung'].append(route)
                return
            if kind == 'fatal':
                return route.fulfill(status=500, content_type='application/json', body='down', headers={
                    'access-control-allow-origin': '*'})
            return route.fulfill(status=200, content_type='application/json', body=OFM, headers={
                'access-control-allow-origin': '*'})
        if '/fonts/' in url or 'glyph' in url:
            phase['glyph'] += 1
            return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
        if 'sprite' in url:
            phase['sprite'] += 1
            return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
        if '.pbf' in url or '/planet/' in url:
            phase['vector'] += 1
            phase['tileErr'] += 1
            return route.fulfill(status=500, content_type='application/octet-stream', body=b'', headers={
                'access-control-allow-origin': '*'})
        route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})

    def block(route):
        outside.append(route.request.url[:140])
        route.abort()

    def release():
        hung = phase['hung'][:]
        phase['hung'].clear()
        for route in hung:
            try:
                route.abort()
            except Exception:
                pass

    action = '#me' if device == 'iPhone 13' else '#xnear'
    with sync_playwright() as p:
        b = p.webkit.launch()
        try:
            iphone = dict(p.devices[device])
            iphone.pop('default_browser_type', None)
            c = b.new_context(**iphone, service_workers='block')
            c.add_init_script(BOOT)
            c.route('**/*', block)
            c.route(BASE + '/**', _local)
            c.route(BASE + '/', _local)
            c.route('**://tile.openstreetmap.org/**', osm)
            c.route('**://*.openfreemap.org/**', ofm)
            pg = c.new_page()
            pg.set_default_timeout(20000)
            pg.on('framenavigated', lambda fr: navs.append(fr.url) if fr == pg.main_frame else None)
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)[:180]))
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='domcontentloaded')
            t0 = time.time()
            blank = None
            end = None
            max_gap = 0
            last = time.time()
            clicked = kind == 'assets'
            while time.time() - t0 < (28 if kind == 'repro' else 22):
                gap = time.time() - last
                if gap > max_gap:
                    max_gap = gap
                last = time.time()
                st = pg.evaluate(STATE)
                if kind != 'assets' and not phase['arm']:
                    px = _shot(pg)
                    if px['tileFrac'] >= 0.35 and st['a'] == 'osm' and not st['canvas']:
                        phase['arm'] = True
                        pg.locator(action).click()
                        clicked = True
                if kind == 'repro' and st['canvas'] and str(st['v']).startswith('loading') and phase['style']:
                    px = _shot(pg)
                    if blank is None or px['tileFrac'] < blank['tileFrac']:
                        blank = px
                if kind == 'assets' and st['a'] == 'openfreemap' and st['v'] == 'ready' and st['canvas']:
                    end = st
                    break
                if kind in ('repro', 'fatal') and st['a'] == 'osm' and str(st['v']).startswith('failed') and not st['canvas'] and st['back'] == 'osm':
                    painted = None
                    for _ in range(25):
                        painted = _shot(pg)
                        if painted['tileFrac'] >= 0.35:
                            break
                        pg.wait_for_timeout(200)
                    end = st
                    end['px'] = painted
                    break
                pg.wait_for_timeout(200)
            trace = pg.evaluate('() => (window.__hmHist || [])')
            loads = pg.evaluate(STATE)['loads']
            if not clicked:
                raise AssertionError('never reached a painted OSM map to %s from %s' % (action, device))
            if end is None:
                raise AssertionError('no result %s %s last=%s style=%s vector=%s errs=%s' % (
                    kind, device, pg.evaluate(STATE), phase['style'], phase['vector'], errs[:3]))
            if loads != 1 or len(navs) != 1:
                raise AssertionError('page loads %s navigations %s (recovery must not reload)' % (loads, navs))
            if outside:
                raise AssertionError('real network: %s' % outside[:4])
            if errs:
                raise AssertionError('page errors: %s' % errs[:3])
            if max_gap > 5:
                raise AssertionError('main thread stalled %.2fs' % max_gap)
            ready = [h for h in trace if h['v'] == 'ready']
            if kind == 'assets':
                if phase['sprite'] < 1 or phase['vector'] < 1 or phase['glyph'] < 1:
                    raise AssertionError('missing-asset path was not exercised %s' % phase)
                px = _shot(pg)
                gl = pg.evaluate("""() => new Promise(done => {
                  var lyr; map.eachLayer(function (l) { if (l.getMaplibreMap) lyr = l; });
                  if (!lyr) return done({err: 'no layer'});
                  var gl = lyr.getMaplibreMap(), cv = gl.getCanvas();
                  gl.once('render', function () {
                    var ctx = cv.getContext('webgl2') || cv.getContext('webgl');
                    var w = cv.width, h = cv.height, lit = 0, land = 0, n = 0, buf = new Uint8Array(4);
                    for (var i = 1; i < 8; i++) for (var j = 1; j < 8; j++) {
                      ctx.readPixels((w * i / 8) | 0, (h * j / 8) | 0, 1, 1, ctx.RGBA, ctx.UNSIGNED_BYTE, buf);
                      n++; if (buf[3] > 0) lit++;
                      if (Math.abs(buf[0] - 168) < 14 && Math.abs(buf[1] - 208) < 14 && Math.abs(buf[2] - 141) < 14) land++;
                    }
                    done({n: n, lit: lit, land: land});
                  });
                  gl.triggerRepaint();
                })""")
                if px['landFrac'] < 0.02 and gl.get('land', 0) < 3:
                    raise AssertionError('backup did not draw land pixels shot=%s gl=%s' % (px, gl))
                if gl.get('lit', 0) < 3:
                    raise AssertionError('canvas has no drawn pixels %s' % gl)
                pg.wait_for_timeout(9000)
                later = pg.evaluate(STATE)
                if later['a'] != 'openfreemap' or later['v'] != 'ready' or later['loads'] != 1 or len(navs) != 1:
                    raise AssertionError('a missing glyph or tile dropped the backup %s navs=%s' % (later, navs))
            else:
                if ready:
                    raise AssertionError('grey backup was marked ready (the main bug) %s' % ready[:4])
                if phase['vector'] != 0:
                    raise AssertionError('grey backup requested %s vector tiles' % phase['vector'])
                if phase['style'] < 1:
                    raise AssertionError('style was never requested')
                if kind == 'repro' and (blank is None or blank['tileFrac'] >= 0.12):
                    raise AssertionError('backup was not a grey/unpainted map %s' % blank)
                if end['px']['tileFrac'] < 0.35:
                    raise AssertionError('recovered map did not draw stand-in pixels %s' % end['px'])
                started = [h for h in trace if h['v'] == 'loading' and h['c']]
                failed = [h for h in trace if str(h['v']).startswith('failed')]
                if not started or not failed:
                    raise AssertionError('missing loading/failed trace %s' % trace[-6:])
                took = (failed[0]['t'] - started[0]['t']) / 1000.0
                if kind == 'repro':
                    if 'no tiles' not in end['v']:
                        raise AssertionError('expected the watchdog, got %s' % end['v'])
                    if not (5 <= took <= 16):
                        raise AssertionError('watchdog took %.2fs (want about 8s)' % took)
                    held = phase['style']
                    phase['again'] = True
                    pg.evaluate('() => map.setView([51.5, -0.12], 12)')
                    pg.wait_for_timeout(2000)
                    later = pg.evaluate(STATE)
                    if later['a'] != 'osm' or later['canvas'] or phase['style'] != held or later['loads'] != 1:
                        raise AssertionError('looped or reloaded %s style %s->%s navs=%s' % (later, held, phase['style'], navs))
                else:
                    if 'no tiles' in end['v'] or not end['v'].startswith('failed:'):
                        raise AssertionError('expected a style failure, got %s' % end['v'])
                    if took >= 6:
                        raise AssertionError('style failure waited %.2fs for the watchdog' % took)
            print('%s %s ok loads=%s navs=%s vector=%s %s' % (
                kind, device, loads, len(navs), phase['vector'], end.get('v') or 'ready'), flush=True)
        finally:
            release()
            b.close()


if __name__ == '__main__':
    if CHILD:
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        run_case(sys.argv[1], sys.argv[2])
    else:
        unittest.main()
