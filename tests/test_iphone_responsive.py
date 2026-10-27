"""iPhone 13 (Playwright WebKit) stays responsive, on the normal map and on the OpenFreeMap backup.

Dean, 27 Oct 2026: on his iPhone the page froze once the map switched to the OpenFreeMap backup
(MapLibre). This check opens this checkout as https://helpmap.uk (served from disk, so the real CSP
applies) in WebKit with the iPhone 13 profile, in two cases:
  normal - OpenStreetMap tiles answered by the CI stand-in tile (check_browser.stub_map_tiles);
  backup - every OpenStreetMap tile refused (403), so tiles.js switches to OpenFreeMap; the
           OpenFreeMap style is the same stand-in style test_tile_fallback.py uses.
After the map has loaded it asserts: no main-thread stall over 500 ms (measured with a timer
heartbeat, because WebKit has no 'longtask' entries), a postcode search for M1 1AE shows results,
the filter buttons and 'Open today only' respond to taps, and the page scrolls.
No real network: postcodes.io is a stand-in answer, and any request to another host fails the test.
"""
import json, mimetypes, os, subprocess, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import check_browser as B

BASE = 'https://helpmap.uk'
MAX_STALL_MS = 500
CASE_LIMIT_S = 150
# Stand-in OpenFreeMap style, identical to tests/test_tile_fallback.py (rule 23: no real vector tiles).
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
# Stand-in postcodes.io answer for M1 1AE (Manchester city centre).
PC = {'status': 200, 'result': {'postcode': 'M1 1AE', 'latitude': 53.4794, 'longitude': -2.2453,
                                'outcode': 'M1', 'admin_district': 'Manchester', 'country': 'England'}}
CARDS = "document.querySelectorAll('#list .card').length"
HEARTBEAT = """(() => { if (window.__hb) return; window.__hb = {last: performance.now(), max: 0, n: 0};
  setInterval(() => { const t = performance.now(), g = t - window.__hb.last; window.__hb.last = t; window.__hb.n++;
    if (g > window.__hb.max) window.__hb.max = g; }, 50); })()"""


def _read(f):
    with open(f, 'rb') as fh:
        return fh.read()


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
    """Poll with evaluate (the site's CSP blocks wait_for_function's eval in WebKit)."""
    for _ in range(secs * 4):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


class IPhoneResponsive(unittest.TestCase):
    def run_case(self, backup):
        from playwright.sync_api import sync_playwright
        bad, outside, errs = [], [], []

        def local(route):
            path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
            f = os.path.join(R, path.lstrip('/'))
            f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f):
                return route.fulfill(status=404, body='')
            route.fulfill(status=200, body=_read(f), headers={
                'content-type': mimetypes.guess_type(f)[0] or 'text/html', 'cache-control': 'no-store'})

        def tiles(route):
            url = route.request.url
            if 'tiles.openfreemap.org' in url:
                if '/styles/' in url:
                    return route.fulfill(status=200, content_type='application/json', body=OFM_STYLE,
                                         headers={'access-control-allow-origin': '*'})
                return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
            if backup:
                return route.fulfill(status=403, content_type='image/png', body=B.TILE_PNG,
                                     headers={'access-control-allow-origin': '*'})
            return route.fulfill(status=200, content_type='image/png', body=B.TILE_PNG,
                                 headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})

        def block(route):
            outside.append(route.request.url[:120])
            route.abort()

        with sync_playwright() as p:
            b = p.webkit.launch()
            c = b.new_context(**p.devices['iPhone 13'], service_workers='block')
            c.route('**/*', block)  # first registered = lowest priority: anything not matched below
            c.route('https://api.postcodes.io/**', lambda r: r.fulfill(
                status=200, content_type='application/json', body=json.dumps(PC),
                headers={'access-control-allow-origin': '*'}))
            c.route(BASE + '/**', local)
            c.route(BASE + '/', local)
            if backup:
                c.route(B.TILE_RE, tiles)
            elif not B.stub_map_tiles(c):
                c.route(B.TILE_RE, tiles)
            pg = c.new_page()
            pg.set_default_timeout(20000)
            pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
            pg.goto(BASE + '/?nocount', wait_until='domcontentloaded')
            self.assertTrue(until(pg, "!!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))", 40), 'map never built')
            if backup:
                ok = until(pg, "window.TILE_ACTIVE==='openfreemap' && !!document.querySelector('#map canvas.maplibregl-canvas, #map .maplibregl-canvas')", 40)
                self.assertTrue(ok, pg.evaluate("({a: window.TILE_ACTIVE, f: window.TILE_FAILOVER || null})"))
            else:
                self.assertTrue(until(pg, "document.querySelectorAll('#map .leaflet-tile-loaded').length > 3", 40), 'no tiles loaded')
                self.assertEqual(pg.evaluate('window.TILE_ACTIVE || "osm"'), 'osm')
            pg.wait_for_timeout(1500)  # map has loaded; start measuring from here
            pg.evaluate(HEARTBEAT)
            pg.wait_for_timeout(500)

            # Postcode search
            pg.fill('#q', 'M1 1AE')
            pg.press('#q', 'Enter')
            if not until(pg, CARDS + ' > 0', 15):
                bad.append('search M1 1AE showed no cards')
            # Filter buttons
            for f in ('walk', 'vouch'):
                sel = '#chips [data-f=%s]' % f
                try:
                    pg.tap(sel, timeout=5000)
                    if not until(pg, "document.querySelector('%s').getAttribute('aria-pressed')==='true'" % sel, 3):
                        bad.append('filter %s did not respond' % f)
                    pg.tap(sel, timeout=5000)
                except Exception as e:
                    bad.append('filter %s not tappable: %s' % (f, str(e)[:100]))
            # Open today only
            try:
                pg.tap('label.tog', timeout=5000)
                if not until(pg, "document.getElementById('openToday').checked && !document.querySelector('.tnote').hidden", 3):
                    bad.append('Open today did not respond')
                pg.tap('label.tog', timeout=5000)
            except Exception as e:
                bad.append('Open today not tappable: %s' % str(e)[:100])
            # Scroll
            pg.evaluate('scrollTo(0, 0)')
            pg.wait_for_timeout(300)
            # Mobile WebKit has no wheel or touch-drag input in Playwright, so scroll the document the
            # way a script would; a frozen main thread or a locked body still fails this.
            pg.evaluate('scrollBy(0, 600)')
            pg.wait_for_timeout(800)
            y = pg.evaluate('scrollY')
            if y < 100:
                bad.append('page did not scroll (scrollY=%s)' % y)
            pg.wait_for_timeout(1000)
            hb = pg.evaluate('window.__hb')
            if hb['max'] > MAX_STALL_MS:
                bad.append('main thread stalled %d ms (> %d) after the map loaded' % (hb['max'], MAX_STALL_MS))
            print('backup' if backup else 'normal', 'max stall %d ms' % hb['max'], 'active', pg.evaluate('window.TILE_ACTIVE || "osm"'))
            c.close()
            b.close()
        if outside:
            bad.append('requests to the real network: %s' % sorted(set(outside))[:5])
        if errs:
            bad.append('page errors: %s' % errs[:3])
        self.assertEqual(bad, [])

    def guarded(self, case):
        """Run one case in a child process. A frozen WebKit page also blocks Playwright's own calls
        (their timeouts never fire), so a hard wall-clock limit turns a freeze into a failure."""
        pr = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), case], cwd=R, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = pr.communicate(timeout=CASE_LIMIT_S)
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9)  # the child and its WebKit
            out, err = pr.communicate()
            self.fail('%s case: page froze, no answer within %d s (main thread blocked)\n%s' % (case, CASE_LIMIT_S, out[-800:]))
        r = subprocess.CompletedProcess(pr.args, pr.returncode, out, err)
        print(r.stdout[-400:])
        self.assertEqual(r.returncode, 0, '%s case failed:\n%s%s' % (case, r.stdout[-1500:], r.stderr[-1500:]))

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_normal_map(self):
        self.guarded('normal')

    # Expected to fail until the light-backup fix lands; remove this decorator in that PR.
    @unittest.expectedFailure
    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_openfreemap_backup(self):
        """XFAIL: iPhone freeze on the OpenFreeMap (MapLibre) backup, Dean 27 Oct 2026. The page stops
        answering taps once the backup map is drawn. Remove expectedFailure when the light backup ships."""
        self.guarded('backup')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] in ('normal', 'backup'):
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        IPhoneResponsive('run_case').run_case(backup=sys.argv[1] == 'backup')
        print(sys.argv[1], 'case passed')
    else:
        unittest.main()
