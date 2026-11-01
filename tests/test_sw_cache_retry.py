"""Offline cache after a first visit (Dean): block tiles, data.js and leaflet, and sw.js must still
serve the copies it precached. The check's one retry must not call that a failure. With the cache
gone, the same block must not be called a pass.

The page is this checkout on 127.0.0.1. Tile hosts are answered here with a blank PNG, then aborted.
Nothing is requested from helpmap.uk or from a map server.
"""
import http.server, os, re, socket, threading, unittest
from urllib.parse import urlparse
R = os.path.join(os.path.dirname(__file__), '..')
import sys
sys.path.insert(0, os.path.join(R, 'scripts'))
try:
    from playwright.sync_api import sync_playwright
    HAVE = True
except Exception:
    HAVE = False

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
TILE_HOSTS = ('tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com')


def _tile(host):
    host = host or ''
    return host in TILE_HOSTS or host.endswith('.tile.openstreetmap.org')


def _cache_name():
    sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
    return re.search(r"const C='([^']+)'", sw).group(1)


def until(page, js, arg=None, timeout=20000):
    """Poll an async predicate with evaluate, which awaits its promise. wait_for_function does not:
    an async function returns a Promise, which is truthy, so it would return at once (the race that
    made this test flaky: the network was blocked before the worker had saved data.js and leaflet.js)."""
    import time
    end = time.time() + timeout / 1000.0
    last = None
    while time.time() < end:
        try:
            last = page.evaluate(js, arg)
        except Exception as e:  # a navigation mid-poll
            last = '%s: %s' % (type(e).__name__, e)
        else:
            if last is True:
                return
        time.sleep(0.25)
    raise AssertionError('timed out waiting for %s (last=%r)' % (js.strip()[:80], last))


class T(unittest.TestCase):
    def test_cached_shell_survives_a_blocked_map_and_a_miss_does_not_pass(self):
        if not HAVE:
            self.skipTest('needs playwright')
        import check_browser as B
        import dark_default
        cache = _cache_name()
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=R, **k)

            def end_headers(self):
                # Keep the bytes out of the HTTP cache. sw.js stores its own copy; a later block
                # must be answered by that cache, not by a disk cache in the browser.
                self.send_header('Cache-Control', 'no-store')
                super().end_headers()

            def do_GET(self):
                path = urlparse(self.path).path
                if blocked['on'] and (path == '/data.js' or path.endswith('/vendor/leaflet.js')):
                    blocked['data' if path == '/data.js' else 'leaflet'] += 1
                    # fetch() has to reject. A 404 would be handed to the page and the cache unused.
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                return super().do_GET()

            def log_message(self, *a):
                pass

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        base = 'http://127.0.0.1:%d/?nocount' % port
        blocked = {'on': False, 'data': 0, 'leaflet': 0, 'tiles': 0}
        leaked = []

        def handle(route):
            req = route.request
            host = urlparse(req.url).hostname or ''
            if _tile(host):
                if blocked['on']:
                    blocked['tiles'] += 1
                    route.abort()
                else:
                    route.fulfill(status=200, body=PNG, headers={
                        'content-type': 'image/png', 'access-control-allow-origin': '*', 'cache-control': 'no-store'})
                return
            if host not in ('127.0.0.1', 'localhost'):
                leaked.append(urlparse(req.url).hostname or req.url.split('?')[0][:120])
                route.abort()
                return
            # Same-origin fetches, including the ones sw.js makes, fall through to the local
            # server. That server is what drops data.js and leaflet once the cache is warm.
            route.continue_()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = B.new_context(
                    browser, color_scheme='dark', viewport={'width': 390, 'height': 844},
                    instagram=True, service_workers='allow')
                context.add_init_script(dark_default.BLOCK)
                context.route('**/*', handle)
                page = context.new_page()
                prime_logs = []
                B.goto(page, base, log=prime_logs.append)
                self.assertEqual(prime_logs, [], prime_logs)
                until(page,
                    """async (name) => {
                        const reg = await navigator.serviceWorker.getRegistration();
                        // The worker must have finished installing (its precache is complete) and control
                        // this page before the network is blocked (redone 1 Nov 2026 from old PR #216).
                        if (!reg || !reg.active || reg.active.state !== 'activated'
                            || !navigator.serviceWorker.controller) return false;
                        const c = await caches.open(name);
                        const urls = (await c.keys()).map(k => k.url);
                        return urls.some(u => /\\/data\\.js(?:\\?|$)/.test(u))
                            && urls.some(u => /\\/vendor\\/leaflet\\.js(?:\\?|$)/.test(u));
                    }""",
                    arg=cache, timeout=20000)
                blocked['on'] = True
                served = []

                def on_response(resp):
                    path = urlparse(resp.url).path or ''
                    host = urlparse(resp.url).hostname or ''
                    if path == '/data.js' or path.endswith('/vendor/leaflet.js') or _tile(host):
                        sw = resp.from_service_worker
                        served.append((host, path, resp.status, sw() if callable(sw) else sw))

                def on_failed(req):
                    if _tile(urlparse(req.url).hostname or ''):
                        blocked['tiles'] += 1

                page2 = context.new_page()
                page2.on('response', on_response)
                page2.on('requestfailed', on_failed)
                logs = []
                B.goto(page2, base, log=logs.append)
                light = page2.evaluate("document.documentElement.classList.contains('light')")
                bg = page2.evaluate("getComputedStyle(document.body).backgroundColor")
                n = page2.evaluate("()=>(window.FB_DATA&&FB_DATA.items&&FB_DATA.items.length)||0")
                pane = page2.evaluate("()=>!!document.querySelector('#map .leaflet-pane')")
                # The network was blocked and the worker still answered. That is not a failed check.
                self.assertEqual(logs, [], logs)
                self.assertGreater(blocked['data'], 0, blocked)
                self.assertGreater(blocked['leaflet'], 0, blocked)
                # Tiles are cache-first: a cached tile never hits the network, an uncached one is aborted.
                # Leaflet may ask for its tiles a moment after the app is ready, so give them up to 10s to arrive.
                for _ in range(40):
                    if blocked['tiles'] or any(_tile(row[0]) and row[3] for row in served):
                        break
                    page2.wait_for_timeout(250)
                tile_hits = [row for row in served if _tile(row[0])]
                self.assertTrue(blocked['tiles'] or any(sw for _, _, _, sw in tile_hits), (blocked, tile_hits))
                self.assertTrue(any(p == '/data.js' and st == 200 and sw for _, p, st, sw in served), served)
                self.assertTrue(any(p.endswith('/vendor/leaflet.js') and st == 200 and sw for _, p, st, sw in served), served)
                self.assertGreater(n, 100, n)
                self.assertTrue(pane)
                self.assertTrue(dark_default.ok_case('blocked', light, bg), (light, bg))
                self.assertFalse(dark_default.ok_case('saved-light', light, bg))
                self.assertEqual(leaked, [], leaked)

                # Same block, empty cache: a miss must fail, and must not be retried into a pass.
                page2.evaluate("""async () => {
                    const keys = await caches.keys();
                    await Promise.all(keys.map(k => caches.delete(k)));
                }""")
                miss_logs = []
                page3 = context.new_page()
                try:
                    B.goto(page3, base, log=miss_logs.append, ready_timeout=2000)
                    self.fail('a cache miss was treated as a pass: %s' % miss_logs)
                except (B.AppNotReady, B.BlockedPage) as err:
                    self.assertNotIn("'ok': True", str(err))
                self.assertLessEqual(len(miss_logs), 1, miss_logs)
                self.assertFalse(any('PASS' in x for x in miss_logs))
                context.close()
                browser.close()
        finally:
            httpd.shutdown()


if __name__ == '__main__':
    unittest.main()
