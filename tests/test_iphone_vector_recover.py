"""Angle B: a backup that starts but never draws must come back to OpenStreetMap and paint.

The live failure (27 Oct 2026): OSM is refused, the map switches to OpenFreeMap, MapLibre's canvas
exists and TILE_VECTOR was set to 'ready' before load, but no vector tiles are requested. Nothing
was listening for MapLibre's 'error', and nothing noticed that load/idle never painted, so the map
stayed grey.

These checks use Playwright WebKit (iPhone 13 and iPhone SE), this checkout served as
https://helpmap.uk, service worker blocked. Tile hosts are stubbed, and a painted tile must be
the 1×1 stand-in: on this WebKit a controlling service worker's tile fetches are not visible to
Playwright and would otherwise leave the machine. The worker-on iPhone checks stay in
test_iphone_map_fix.py. Nothing here contacts a public tile server.

  stuck — the OpenFreeMap style request is left unanswered, so the layer starts and never draws.
          About 8s later the watchdog must return to OpenStreetMap once, the stand-in tiles must
          paint, and a later run of OSM refusals must not open OpenFreeMap again.
  error — the style answers 500. MapLibre's 'error' event must fail the layer without waiting out
          the watchdog, then OpenStreetMap paints.
  draws — the stand-in style paints. The layer must reach 'ready' on that real load and still be
          OpenFreeMap after the watchdog has had time to fire.
"""
import mimetypes, os, subprocess, sys, time, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = 'https://helpmap.uk'
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
OFM = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
       '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
       '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
       '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
STATE = """() => ({
  a: window.TILE_ACTIVE,
  v: window.TILE_VECTOR || '',
  canvas: !!document.querySelector('#map .leaflet-gl-layer canvas'),
  imgs: [...document.querySelectorAll('#map img.leaflet-tile-loaded')].map(i => ({src: i.src, w: i.naturalWidth})),
  back: (window.TILE_FAILOVER || {}).back || null,
  sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller)
})"""
# WebKit + Playwright does not keep a service worker as the controller across a reload while
# routes are intercepted. The page is claimed in place (clients.claim); the measured run is a
# fresh addTiles after that, and this trace still sees a backup that starts and ends between polls.
TRACE = """(() => { window.__hmHist = []; setInterval(() => { var c = false;
  try { c = !!document.querySelector('#map .leaflet-gl-layer canvas'); } catch (e) {}
  window.__hmHist.push({t: performance.now(), a: window.TILE_ACTIVE || '', v: window.TILE_VECTOR || '', c: c});
  if (window.__hmHist.length > 500) window.__hmHist.shift(); }, 40); })()"""
LIMIT = {'stuck': 45, 'error': 30, 'draws': 40}


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def snap(pg):
    raw = pg.evaluate(STATE)
    imgs = raw.pop('imgs')
    raw['n'] = len(imgs)
      # The stand-in tile is 1×1. A real OpenStreetMap tile is 256×256 and must not count.
    raw['painted'] = sum(1 for i in imgs if 'tile.openstreetmap.org' in (i.get('src') or '') and i.get('w') == 1)
    return raw


class Source(unittest.TestCase):
    def test_backup_failure_is_wired_to_one_return(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertIn("gl.on('error'", tiles)
        self.assertIn("gl.on('load'", tiles)
        self.assertIn("gl.on('idle'", tiles)
        self.assertIn('window.TILE_VECTOR_WATCH_MS = 8000', tiles)
        self.assertIn("new Error('no tiles')", tiles)
        self.assertIn("window.TILE_VECTOR = 'loading'", tiles)
        self.assertIn("window.TILE_VECTOR = 'ready'", tiles)
        self.assertNotRegex(tiles, r"addTo\(map\);\s*window\.TILE_VECTOR = 'ready'")
        self.assertIn('vectorFailed = true', tiles)


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
        print((out or '')[-500:])
        self.assertEqual(pr.returncode, 0, '%s %s failed:\n%s%s' % (kind, device, out[-1500:], err[-1500:]))

    def test_backup_that_never_draws_returns_to_osm_and_paints(self):
        for device in ('iPhone 13', 'iPhone SE'):
            self._guarded('stuck', device)

    def test_maplibre_error_returns_to_osm_without_waiting_for_the_watchdog(self):
        for device in ('iPhone 13', 'iPhone SE'):
            self._guarded('error', device)

    def test_backup_that_paints_stays_ready_past_the_watchdog(self):
        for device in ('iPhone 13', 'iPhone SE'):
            self._guarded('draws', device)


def _local(route):
    path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
    f = os.path.join(R, path.lstrip('/'))
    f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
    if not os.path.isfile(f):
        return route.fulfill(status=404, body='')
    route.fulfill(status=200, body=open(f, 'rb').read(), headers={
        'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})


def run_case(kind, device):
    from playwright.sync_api import sync_playwright
    phase = {'osm': 0, 'ofm': 0, 'again': False, 'hung': []}
    outside = []

    def osm(route):
        phase['osm'] += 1
        # Three refusals switch to the backup. After it has given up, further refusals must not switch back.
        bad = phase['osm'] <= 3 or phase['again']
        route.fulfill(status=403 if bad else 200, content_type='image/png', body=PNG, headers={
            'access-control-allow-origin': '*', 'cache-control': 'no-store'})

    def ofm(route):
        phase['ofm'] += 1
        if kind == 'stuck':
            phase['hung'].append(route)
            return
        if kind == 'error':
            return route.fulfill(status=500, content_type='application/json', body='down', headers={
                'access-control-allow-origin': '*'})
        if '/styles/' in route.request.url:
            return route.fulfill(status=200, content_type='application/json', body=OFM, headers={
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

    with sync_playwright() as p:
        b = p.webkit.launch()
        try:
            iphone = dict(p.devices[device])
            iphone.pop('default_browser_type', None)
            c = b.new_context(**iphone, service_workers='block')
            c.add_init_script(TRACE)
            c.route('**/*', block)
            c.route(BASE + '/**', _local)
            c.route(BASE + '/', _local)
            c.route('**://tile.openstreetmap.org/**', osm)
            c.route('**://*.openfreemap.org/**', ofm)
            pg = c.new_page()
            pg.set_default_timeout(20000)
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)[:180]))
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='domcontentloaded')
            t0 = time.time()
            saw_start = False
            max_gap = 0
            last = time.time()
            end = None
            while time.time() - t0 < 22:
                st = snap(pg)
                gap = time.time() - last
                if saw_start and gap > max_gap:
                    max_gap = gap
                last = time.time()
                if st['v'] == 'loading' and st['canvas']:
                    saw_start = True
                if kind == 'draws' and st['a'] == 'openfreemap' and st['v'] == 'ready' and st['canvas']:
                    end = st
                    break
                if kind in ('stuck', 'error') and st['a'] == 'osm' and st['v'].startswith('failed') and st['painted'] >= 4 and st['back'] == 'osm' and not st['canvas']:
                    end = st
                    break
                pg.wait_for_timeout(200)
            trace = pg.evaluate('() => ({t0: window.__hmT0 || 0, h: window.__hmHist || []})')
            started = [h for h in trace['h'] if h['t'] >= trace['t0'] - 1 and h['v'] == 'loading' and h['c']]
            failed = [h for h in trace['h'] if h['t'] >= trace['t0'] - 1 and str(h['v']).startswith('failed')]
            ready = [h for h in trace['h'] if h['t'] >= trace['t0'] - 1 and h['v'] == 'ready']
            if end is None:
                raise AssertionError('no result %s %s last=%s ofm=%s errs=%s' % (kind, device, snap(pg), phase['ofm'], errs[:3]))
            if not started:
                raise AssertionError('backup never started %s hist=%s' % (end, trace['h'][-8:]))
            took = ((failed or ready)[0]['t'] - started[0]['t']) / 1000.0
            if kind == 'stuck':
                if 'no tiles' not in end['v']:
                    raise AssertionError('expected the watchdog, got %s' % end['v'])
                if not (5 <= took <= 16):
                    raise AssertionError('watchdog took %.2fs (want about 8s) %s' % (took, end))
                held = phase['ofm']
                phase['again'] = True
                before = phase['osm']
                pg.evaluate('() => map.setView([53.48, -2.24], 12)')
                pg.wait_for_timeout(2500)
                later = snap(pg)
                if later['a'] != 'osm' or later['canvas'] or phase['ofm'] != held:
                    raise AssertionError('looped back to the backup %s ofm %s->%s' % (later, held, phase['ofm']))
                if phase['osm'] < before + 3:
                    raise AssertionError('panning did not ask for new OSM tiles (%s then %s)' % (before, phase['osm']))
                if max_gap > 5:
                    raise AssertionError('main thread stalled %.2fs while the backup hung' % max_gap)
            elif kind == 'error':
                if 'no tiles' in end['v'] or not end['v'].startswith('failed:'):
                    raise AssertionError('expected a MapLibre error, got %s' % end['v'])
                if took >= 6:
                    raise AssertionError('error path waited %.2fs for the watchdog %s' % (took, end['v']))
            else:
                pg.wait_for_timeout(9000)
                later = snap(pg)
                if later['a'] != 'openfreemap' or later['v'] != 'ready' or not later['canvas'] or later['back']:
                    raise AssertionError('painted backup did not stay %s' % later)
            if outside:
                raise AssertionError('real network: %s' % outside[:4])
            if errs:
                raise AssertionError('page errors: %s' % errs[:3])
            print('%s %s ok in %.2fs tiles=%s %s' % (kind, device, took, end['painted'], end['v'] or 'ready'), flush=True)
        finally:
            release()
            b.close()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] in LIMIT:
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        run_case(sys.argv[1], sys.argv[2])
    else:
        unittest.main()
