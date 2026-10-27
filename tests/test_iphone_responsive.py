"""iPhone 13 and iPhone SE (Playwright WebKit) stay responsive, on the normal map and on the OpenFreeMap backup.

Dean, 27 Oct 2026: on his iPhone the page froze once the map switched to the OpenFreeMap backup
(MapLibre). The same day: the test browser must match a real iPhone, so the service worker is
allowed. Blocking it made the OpenFreeMap style fetch come back as image/png and the map stay grey.
That was a test artefact, not the phone.

This check opens this checkout as https://helpmap.uk (served from disk, so the real CSP applies)
in WebKit with the iPhone 13 profile and the iPhone SE profile, in two cases:
  normal - OpenStreetMap tiles answered by the local stand-in (HTTP 200 PNG);
  backup - every OpenStreetMap tile is HTTP 403 from that server, so tiles.js switches to
           OpenFreeMap. The style document is JSON from the same server, not a Playwright route().
After the map has loaded it asserts: no main-thread stall over 500 ms (measured with a timer
heartbeat, because WebKit has no 'longtask' entries), a postcode search for M1 1AE shows results,
the filter buttons and 'Open today only' respond to taps, and the page scrolls.
No real network: the proxy answers postcodes.io itself and records any other host, which fails the test.
"""
import json, os, subprocess, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iphone_webkit import DEVICES, iphone_context
from standin_net import Proxy, StandIn

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
    def run_case(self, backup, device='iPhone 13'):
        from playwright.sync_api import sync_playwright
        bad, errs = [], []
        stand = StandIn(R, style=OFM_STYLE)
        pc = json.dumps(PC).encode()

        def decide(host, path):
            # Real responses from the stand-in. No route() on the style or on the tiles.
            if host == 'tile.openstreetmap.org' or host.endswith('.tile.openstreetmap.org'):
                if backup:
                    return stand.png(403)
                return stand.png(200, stub=True)
            if 'openfreemap.org' in host:
                low = path.lower()
                if '/styles/' in low or low.endswith('.json') or 'tilejson' in low:
                    return stand.json_style()
                return stand.empty(404)
            if host == 'api.postcodes.io':
                return stand.json_body(pc)
            if host in ('helpmap.uk', 'www.helpmap.uk'):
                return stand.site_file(path)
            stand.other.append(host + path[:80])
            return stand.empty(403)

        stand.decide = decide
        proxy = Proxy(stand)
        try:
            self._run_page(sync_playwright, proxy, stand, backup, device, bad, errs)
        finally:
            proxy.stop()
            stand.stop()
        if stand.other:
            bad.append('requests to the real network: %s' % sorted(set(stand.other))[:5])
        if stand.errors:
            bad.append('stand-in errors: %s' % stand.errors[:3])
        if errs:
            bad.append('page errors: %s' % errs[:3])
        self.assertEqual(bad, [])

    def _run_page(self, sync_playwright, proxy, stand, backup, device, bad, errs):
        with sync_playwright() as p:
            b = p.webkit.launch()
            # Default iPhone WebKit context: service worker allowed, same as the phone.
            c = iphone_context(p, b, device, proxy=proxy)
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
            print(device, 'backup' if backup else 'normal', 'max stall %d ms' % hb['max'], 'active', pg.evaluate('window.TILE_ACTIVE || "osm"'), 'sw', pg.evaluate("() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)"))
            c.close()
            b.close()

    def guarded(self, case, device):
        """Run one case in a child process. A frozen WebKit page also blocks Playwright's own calls
        (their timeouts never fire), so a hard wall-clock limit turns a freeze into a failure."""
        pr = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), case, device], cwd=R, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = pr.communicate(timeout=CASE_LIMIT_S)
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9)  # the child and its WebKit
            out, err = pr.communicate()
            self.fail('%s %s case: page froze, no answer within %d s (main thread blocked)\n%s' % (device, case, CASE_LIMIT_S, out[-800:]))
        r = subprocess.CompletedProcess(pr.args, pr.returncode, out, err)
        print(r.stdout[-400:])
        self.assertEqual(r.returncode, 0, '%s %s case failed:\n%s%s' % (device, case, r.stdout[-1500:], r.stderr[-1500:]))

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_normal_map_iphone_13(self):
        self.guarded('normal', 'iPhone 13')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_normal_map_iphone_se(self):
        self.guarded('normal', 'iPhone SE')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_openfreemap_backup_iphone_13(self):
        """Dean 27 Oct 2026: the page froze on the OpenFreeMap (MapLibre) backup at the first filter tap
        (map max zoom was Infinity, so the marker cluster rebuild never ended). Fixed in tiles.js.
        Service worker on, failure injected by the local server (HTTP 403), not route()."""
        self.guarded('backup', 'iPhone 13')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_openfreemap_backup_iphone_se(self):
        """Same backup check on iPhone SE. Service worker on."""
        self.guarded('backup', 'iPhone SE')


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] in ('normal', 'backup') and sys.argv[2] in DEVICES:
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        IPhoneResponsive('run_case').run_case(backup=sys.argv[1] == 'backup', device=sys.argv[2])
        print(sys.argv[2], sys.argv[1], 'case passed')
    else:
        unittest.main()
