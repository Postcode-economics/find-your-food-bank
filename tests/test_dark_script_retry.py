"""The deploy check on run 40305441261 failed one case, dark + storage blocked:

    FAIL chromium dark blocked dark error app not ready
    {'ok': False, 'n': 0, 'pane': False, 'wall': False,
     'title': 'Find a food bank, warm space or shelter near you – helpmap.uk'}

The document was the real page (the title, and wall was false). The map never started, which is
what happens when data.js does not run. These tests reproduce that offline: the first data.js
answer is a challenge page, or the HTML is cut off, or tile hosts never respond. Nothing here
contacts helpmap.uk or a tile server. A page that does load and is the wrong theme still fails.
"""
import mimetypes, os, re, time, unittest
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
CHALLENGE = b'<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>Checking your browser before accessing helpmap.uk. <script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script></body></html>'
TILE_HOSTS = ('tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com', 'tiles.openfreemap.org')


def _tile(host):
    host = host or ''
    return host in TILE_HOSTS or host.endswith('.tile.openstreetmap.org')


def _file(path):
    rel = (path or '/').lstrip('/')
    f = os.path.join(R, rel) if rel else R
    if os.path.isdir(f):
        f = os.path.join(f, 'index.html')
    return f


def _ctype(path):
    """Type from the file we actually serve. The document URL is "/", and guessing that is
    application/octet-stream, which makes Chromium download it and abort the navigation."""
    path = path or ''
    if path.endswith('.js'):
        return 'text/javascript'
    if path.endswith('.json'):
        return 'application/json'
    if path.endswith('.css'):
        return 'text/css'
    if path.endswith('.svg'):
        return 'image/svg+xml'
    if path.endswith(('.html', '.htm')) or path in ('', '/'):
        return 'text/html'
    return mimetypes.guess_type(path)[0] or 'application/octet-stream'


def _bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _page_build():
    """The build named in this checkout's HTML. version.json has to say the same thing, or the
    page's self-heal reloads and the navigation comes back net::ERR_ABORTED."""
    with open(os.path.join(R, 'index.html'), encoding='utf-8') as fh:
        head = fh.read(8000)
    m = re.search(r'helpmap-build" content="([^"]+)"', head)
    if not m:
        raise AssertionError('index.html has no helpmap-build')
    return m.group(1)


def _version():
    return ('{"build":"%s"}' % _page_build()).encode()


class T(unittest.TestCase):
    def setUp(self):
        if not HAVE:
            self.skipTest('needs playwright')
        import dark_default
        self._exists = dark_default.os.path.exists
        # The failing job used Playwright's Chromium, not a system Chrome.
        dark_default.os.path.exists = lambda p: False if p == '/usr/bin/google-chrome' else self._exists(p)

    def tearDown(self):
        if HAVE:
            import dark_default
            dark_default.os.path.exists = self._exists

    def _install(self, data_js):
        """Route every browser request. data_js(request, docs) returns a body to replace data.js, or None."""
        import check_browser as B
        leaked, docs = [], {'n': 0, 'ig': 0}
        orig = B.new_context

        def handler(route):
            req = route.request
            url = req.url
            host = urlparse(url).hostname or ''
            if _tile(host):
                route.fulfill(status=200, body=PNG, headers={
                    'content-type': 'image/png', 'access-control-allow-origin': '*'})
                return
            if host != 'helpmap.uk':
                leaked.append(url.split('?')[0][:140])
                route.abort()
                return
            path = urlparse(url).path or '/'
            ua = (req.headers.get('user-agent') or req.headers.get('User-Agent') or '')
            if req.resource_type == 'document':
                docs['n'] += 1
                if 'Instagram' in ua:
                    docs['ig'] += 1
            if path.endswith('version.json'):
                route.fulfill(status=200, body=_version(), headers={'content-type': 'application/json'})
                return
            if path.endswith('data.js'):
                body = data_js(req, docs)
                if body is not None:
                    route.fulfill(status=200, body=body, headers={'content-type': 'text/html; charset=UTF-8'})
                    return
            f = _file(path)
            if not os.path.isfile(f):
                route.fulfill(status=404, body=b'', headers={'content-type': 'text/plain'})
                return
            route.fulfill(status=200, body=_bytes(f), headers={'content-type': _ctype(f)})

        def wrapped(browser, **kw):
            c = orig(browser, **kw)
            c.route('**/*', handler)
            return c

        B.new_context = wrapped
        self.addCleanup(setattr, B, 'new_context', orig)
        return leaked, docs

    def test_dark_blocked_challenge_script_is_retried_and_theme_still_checked(self):
        import io, contextlib, dark_default
        # The third Instagram document is chromium / dark / blocked, the case that failed in CI.
        seen = {'n': 0}

        def data_js(req, docs):
            if docs['ig'] == 3 and seen['n'] == 0:
                seen['n'] += 1
                return CHALLENGE
            return None

        leaked, docs = self._install(data_js)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bad = dark_default.run('https://helpmap.uk', ['chromium'])
        out = buf.getvalue()
        self.assertEqual(leaked, [], leaked)
        self.assertEqual(bad, [], out)
        self.assertEqual(seen['n'], 1)
        self.assertIn('retry: challenge page in place of a script', out)
        self.assertIn('data.js', out)
        self.assertNotIn('FAIL', out)
        self.assertEqual(out.count('PASS chromium'), 12)
        self.assertIn('PASS chromium dark blocked dark rgb(10, 22, 40)', out)
        # The recovered dark page must not also satisfy the only case that is allowed to be light.
        self.assertTrue(dark_default.ok_case('blocked', False, 'rgb(10, 22, 40)'))
        self.assertFalse(dark_default.ok_case('saved-light', False, 'rgb(10, 22, 40)'))
        self.assertFalse(dark_default.ok_case('fresh', True, 'rgb(255, 255, 255)'))

    def test_a_challenge_script_that_persists_still_fails(self):
        import io, contextlib, dark_default

        def data_js(req, docs):
            return CHALLENGE

        leaked, docs = self._install(data_js)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bad = dark_default.run('https://helpmap.uk', ['chromium'])
        out = buf.getvalue()
        self.assertEqual(leaked, [], leaked)
        self.assertEqual(len(bad), 12, out)
        self.assertNotIn('\nPASS ', '\n' + out)
        self.assertEqual(out.count('retry: challenge page in place of a script'), 12)  # once each, not a loop
        self.assertIn('text/html', out)
        self.assertIn('data.js', out)
        self.assertIn('dark blocked', out)

    def test_truncated_html_retries_once_then_checks_the_theme(self):
        import check_browser as B, dark_default
        with open(os.path.join(R, 'index.html'), encoding='utf-8') as fh:
            html = fh.read()
        cut = html[:html.find('</title>') + len('</title>')] + '</head><body></body></html>'
        first = {'n': 0}
        logs = []

        def handler(route):
            req = route.request
            host = urlparse(req.url).hostname or ''
            if _tile(host):
                route.fulfill(status=200, body=PNG, headers={'content-type': 'image/png', 'access-control-allow-origin': '*'})
                return
            if host != 'helpmap.uk':
                route.abort()
                return
            path = urlparse(req.url).path or '/'
            if req.resource_type == 'document' and first['n'] == 0:
                first['n'] = 1
                route.fulfill(status=200, body=cut.encode(), headers={'content-type': 'text/html'})
                return
            if path.endswith('version.json'):
                route.fulfill(status=200, body=_version(), headers={'content-type': 'application/json'})
                return
            f = _file(path)
            if not os.path.isfile(f):
                route.fulfill(status=404, body=b'')
                return
            route.fulfill(status=200, body=_bytes(f), headers={'content-type': _ctype(f)})

        with sync_playwright() as p:
            b = p.chromium.launch()
            c = B.new_context(b, color_scheme='dark', viewport={'width': 390, 'height': 844}, instagram=True)
            c.add_init_script(dark_default.BLOCK)
            c.route('**/*', handler)
            pg = c.new_page()
            t0 = time.monotonic()
            B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append)
            elapsed = time.monotonic() - t0
            light = pg.evaluate("document.documentElement.classList.contains('light')")
            bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
            c.close(); b.close()
        self.assertLess(elapsed, 10, logs)  # did not sit on the 15s ready timeout
        self.assertTrue(any('no data.js' in x for x in logs), logs)
        self.assertEqual(len(logs), 1)
        self.assertTrue(dark_default.ok_case('blocked', light, bg), (light, bg))
        self.assertFalse(dark_default.ok_case('saved-light', light, bg))

    def test_blocked_tiles_do_not_stop_the_app_becoming_ready(self):
        import check_browser as B, dark_default
        leaked = []

        def handler(route):
            host = urlparse(route.request.url).hostname or ''
            if _tile(host):
                route.abort()
                return
            if host != 'helpmap.uk':
                leaked.append(route.request.url.split('?')[0][:140])
                route.abort()
                return
            path = urlparse(route.request.url).path or '/'
            if path.endswith('version.json'):
                route.fulfill(status=200, body=_version(), headers={'content-type': 'application/json'})
                return
            f = _file(path)
            if not os.path.isfile(f):
                route.fulfill(status=404, body=b'')
                return
            route.fulfill(status=200, body=_bytes(f), headers={'content-type': _ctype(f)})

        with sync_playwright() as p:
            b = p.chromium.launch()
            c = B.new_context(b, color_scheme='dark', viewport={'width': 390, 'height': 844}, instagram=True)
            c.add_init_script(dark_default.BLOCK)
            c.route('**/*', handler)
            pg = c.new_page()
            logs = []
            t0 = time.monotonic()
            B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append)
            elapsed = time.monotonic() - t0
            light = pg.evaluate("document.documentElement.classList.contains('light')")
            bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
            c.close(); b.close()
        self.assertEqual(leaked, [], leaked)
        self.assertEqual(logs, [])  # a blocked tile is not a script failure and not a retry
        self.assertLess(elapsed, 8, elapsed)
        self.assertTrue(dark_default.ok_case('blocked', light, bg), (light, bg))


if __name__ == '__main__':
    unittest.main()
