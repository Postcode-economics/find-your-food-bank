"""Offline caches when the map or the core scripts fail to load.

The first visit is this checkout on 127.0.0.1. Tile hosts and helpmap.uk are not resolved, and a
tile image is answered here. sw.js precaches data.js and leaflet.js. One tile is stored in the
worker's tile cache (the first paint asks for tiles before the worker has claimed the page). Then
data.js, leaflet.js and tiles are cut: the worker still serves the cached copies, and that ready
page is not a retry. With those cache entries removed, the same cut is a failure, tried once.
"""
import base64, os, re, socket, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
BLOCKED = ('/data.js', '/vendor/leaflet.js')
# A service-worker fetch() does not go through Playwright's route. These hosts must not resolve,
# or that fetch would leave the machine. The route still answers a tile the page asks for directly.
_DNS = ('--host-resolver-rules=' + ', '.join(
    'MAP %s ~NOTFOUND' % host for host in (
        'tile.openstreetmap.org', '*.tile.openstreetmap.org', 'api.maptiler.com',
        'tiles.stadiamaps.com', 'helpmap.uk', '*.helpmap.uk')))


def _tile(host):
    host = host or ''
    return host in TILE_HOSTS or host.endswith('.tile.openstreetmap.org')


def _ctype(path):
    ext = os.path.splitext(path)[1]
    return {'.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
            '.svg': 'image/svg+xml', '.png': 'image/png', '.html': 'text/html',
            '.ico': 'image/x-icon'}.get(ext, 'application/octet-stream')


def _cache_names():
    sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
    return re.search(r"const C='([^']+)'", sw).group(1), re.search(r"\bT='([^']+)'", sw).group(1)


class _Handler(BaseHTTPRequestHandler):
    block = False

    def do_GET(self):
        path = urlparse(self.path).path
        # A reset, not a 503: the worker substitutes its cache only when fetch() itself fails.
        if self.block and path in BLOCKED:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            return
        rel = path.lstrip('/') or 'index.html'
        f = os.path.join(R, rel)
        if os.path.isdir(f):
            f = os.path.join(f, 'index.html')
        if not os.path.isfile(f):
            self.send_response(404)
            self.end_headers()
            return
        data = open(f, 'rb').read()
        self.send_response(200)
        self.send_header('content-type', _ctype(f))
        self.send_header('content-length', str(len(data)))
        self.send_header('cache-control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@unittest.skipUnless(HAVE, 'needs playwright')
class OfflineCache(unittest.TestCase):
    def test_cached_copies_are_not_a_failure_and_a_miss_is_not_a_pass(self):
        import check_browser as B
        shell, tiles = _cache_names()
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/?nocount' % httpd.server_address[1]
        leaked = []

        def handler(route):
            req = route.request
            host = urlparse(req.url).hostname or ''
            path = urlparse(req.url).path or '/'
            if _tile(host):
                if _Handler.block:
                    route.abort('connectionfailed')
                else:
                    route.fulfill(status=200, body=PNG, headers={
                        'content-type': 'image/png', 'access-control-allow-origin': '*',
                        'cache-control': 'no-store'})
                return
            if host not in ('127.0.0.1', 'localhost'):
                leaked.append(req.url.split('?')[0][:140])
                route.abort()
                return
            if _Handler.block and path in BLOCKED:
                route.abort('connectionfailed')
                return
            route.fallback()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(args=[_DNS])
                context = B.new_context(
                    browser, viewport={'width': 390, 'height': 700}, service_workers='allow')
                context.route('**/*', handler)
                page = context.new_page()
                warm = []
                B.goto(page, base, log=warm.append)
                self.assertEqual(warm, [])
                controlled = False
                for _ in range(50):
                    controlled = page.evaluate(
                        "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)")
                    if controlled:
                        break
                    page.wait_for_timeout(100)
                self.assertTrue(controlled, 'service worker did not claim the page')
                cached = page.evaluate(
                    """async (shell) => {
                      const c = await caches.open(shell);
                      return (await c.keys()).map(k => new URL(k.url).pathname);
                    }""",
                    shell)
                self.assertIn('/data.js', cached)
                self.assertIn('/vendor/leaflet.js', cached)
                page.evaluate(
                    """async ([name, b64]) => {
                      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                      const c = await caches.open(name);
                      await c.put('https://tile.openstreetmap.org/5/15/9.png',
                        new Response(bytes, {status: 200, headers: {'content-type': 'image/png'}}));
                    }""",
                    [tiles, base64.b64encode(PNG).decode()])

                _Handler.block = True
                served = []
                t0 = time.monotonic()
                B.goto(page, base, log=served.append)
                ready = page.evaluate(
                    "()=>({n:(window.FB_DATA&&FB_DATA.items&&FB_DATA.items.length)||0,"
                    "pane:!!document.querySelector('#map .leaflet-pane')})")
                tile_bytes = page.evaluate(
                    """async () => {
                      const r = await fetch('https://tile.openstreetmap.org/5/15/9.png');
                      return (await r.arrayBuffer()).byteLength;
                    }""")
                self.assertEqual(served, [], served)  # a copy the worker served is not a failure
                self.assertGreater(ready['n'], 100, ready)
                self.assertTrue(ready['pane'], ready)
                self.assertEqual(tile_bytes, len(PNG))  # the blocked tile host was not asked
                self.assertLess(time.monotonic() - t0, 10, served)
                self.assertEqual(leaked, [], leaked)

                page.evaluate(
                    """async ([shell, tiles]) => {
                      const c = await caches.open(shell);
                      for (const k of await c.keys()) {
                        const path = new URL(k.url).pathname;
                        if (path === '/data.js' || path === '/vendor/leaflet.js') await c.delete(k);
                      }
                      const t = await caches.open(tiles);
                      for (const k of await t.keys()) await t.delete(k);
                    }""",
                    [shell, tiles])
                missed = []
                t1 = time.monotonic()
                with self.assertRaises(B.AppNotReady) as cm:
                    B.goto(page, base + '&miss=1', log=missed.append, ready_timeout=5000)
                self.assertEqual(len(missed), 1, missed)  # one retry, and the failure is not a pass
                self.assertTrue(missed[0].startswith('retry:'), missed)
                self.assertIn('data.js', missed[0])
                self.assertIn("'n': 0", str(cm.exception))
                # ready_timeout is 5s and the miss is tried once, so this is about 10s plus the
                # navigation. It must still fail in this attempt, not sit out two full 15s waits.
                self.assertLess(time.monotonic() - t1, 15, missed)
                self.assertEqual(leaked, [], leaked)
                context.close()
                browser.close()
        finally:
            _Handler.block = False
            httpd.shutdown()


if __name__ == '__main__':
    unittest.main()
