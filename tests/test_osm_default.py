"""OpenStreetMap is the permanent default map (26 Oct 2026).

The MapTiler key is dead (403 Invalid key). It must not come back in a site file, MapTiler must not be the
provider the map starts on, and reverting any commit since v88 (the one deploy-check refuses to undo)
must still leave OpenStreetMap as that default. A first visit caches OpenStreetMap tiles; after the
service-worker version changes, a MapTiler entry is gone and a later offline visit still shows the cached
OpenStreetMap tiles. Tile hosts are answered with a blank PNG. Nothing here contacts a map server or the live site.
"""
import http.server, os, re, shutil, ssl, struct, subprocess, tempfile, threading, unittest, zlib
from urllib.parse import urlparse
R = os.path.join(os.path.dirname(__file__), '..')
DEAD = 'xl3BtUpx' + 'Qak69583G9Q6'
FIELD = re.compile(r"name:\s*'maptiler'\s*,\s*key:\s*'([^']*)'")
URLKEY = re.compile(r"https://api\.maptiler\.com\S*?[?&]key=(?!\{key\})([^&\s'\"<>]+)")
V88 = 'ad54c561'


def providers(text):
    body = re.search(r"TILE_PROVIDERS\s*=\s*\[(.*?)\];", text, re.S)
    if not body:
        return []
    out = []
    for chunk in re.split(r"(?=name:\s*')", body.group(1)):
        name = re.search(r"name:\s*'(\w+)'", chunk)
        url = re.search(r"url:\s*'([^']*)'", chunk)
        key = re.search(r"key:\s*'([^']*)'", chunk)
        if name and url:
            out.append({'name': name.group(1), 'url': url.group(1), 'key': key.group(1) if key else ''})
    return out


def first_usable(text):
    """Same rule as tiles.js: the first provider with a key, or whose URL needs no key."""
    for p in providers(text):
        if '{key}' not in p['url'] or p['key']:
            return p['name']
    return None


def site_paths():
    out = subprocess.check_output(['git', 'ls-files', '-z'], cwd=R)
    for path in out.decode().split('\0'):
        if path and not path.startswith('tests/'):
            yield path


def solid_png(w, h, rgba):
    raw = b''.join(b'\x00' + bytes(rgba) * w for _ in range(h))
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


class KeysAndDefault(unittest.TestCase):
    def test_no_maptiler_key_and_osm_is_first(self):
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertEqual(providers(tiles)[0]['name'], 'osm')
        self.assertEqual(first_usable(tiles), 'osm')
        self.assertEqual(FIELD.search(tiles).group(1), '')
        bad = []
        for path in site_paths():
            try:
                text = open(os.path.join(R, path), encoding='utf-8').read()
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            if DEAD in text:
                bad.append(path + ': dead MapTiler key')
            found = FIELD.search(text)
            if found and found.group(1):
                bad.append(path + ': MapTiler key field')
            if URLKEY.search(text):
                bad.append(path + ': MapTiler key in a URL')
        self.assertEqual(bad, [])

    def test_worker_caches_osm_and_drops_maptiler_on_version_bump(self):
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        self.assertIn("(^|\\.)tile\\.openstreetmap\\.org$", sw)
        self.assertIn('MAPTILER', sw)
        self.assertIn("const C='fyfb-v96'", sw)
        # The tile cache is kept across a version bump; MapTiler entries in it are deleted on activate.
        self.assertIn('x!==C&&x!==T', sw)
        self.assertIn('c.delete(r)', sw)
        self.assertLess(sw.index('MAPTILER.test(u.host)'), sw.index('const hit=await c.match(url)'))


class RevertSinceV88(unittest.TestCase):
    def test_every_revert_leaves_osm(self):
        found = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', V88 + '^{commit}'],
                               cwd=R, capture_output=True, text=True)
        if found.returncode != 0:
            self.skipTest('commit %s is not in this checkout (shallow clone?); fetch full history to run this' % V88)
        v88 = found.stdout.strip()
        commits = subprocess.check_output(['git', 'rev-list', '--reverse', v88 + '..HEAD'], cwd=R, text=True).split()
        self.assertGreater(len(commits), 0)
        d = tempfile.mkdtemp()
        script = os.path.join(R, 'scripts', 'revert_site.sh')
        try:
            subprocess.check_call(['git', 'clone', '--shared', '--quiet', R, d])
            subprocess.check_call(['git', 'config', 'user.email', 't@t'], cwd=d)
            subprocess.check_call(['git', 'config', 'user.name', 't'], cwd=d)
            base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=d, text=True).strip()
            for sha in commits:
                subprocess.check_call(['git', 'reset', '--hard', '-q', base], cwd=d)
                subprocess.check_call(['git', 'clean', '-fdq'], cwd=d)
                subprocess.check_call(['bash', script, sha], cwd=d)
                tiles = open(os.path.join(d, 'tiles.js'), encoding='utf-8').read()
                self.assertNotIn(DEAD, tiles, sha)
                self.assertEqual(first_usable(tiles), 'osm', sha)
                found = FIELD.search(tiles)
                self.assertTrue(found and found.group(1) == '', sha)
                grep = subprocess.run(['git', 'grep', '-l', '-F', DEAD], cwd=d, capture_output=True, text=True)
                hits = [h for h in grep.stdout.splitlines() if h and not h.startswith('tests/')]
                self.assertEqual(hits, [], sha)
        finally:
            shutil.rmtree(d)


def until(page, js, secs=20):
    """Poll with evaluate. wait_for_function uses eval, which this site's CSP refuses."""
    for _ in range(secs * 4):
        try:
            if page.evaluate(js):
                return True
        except Exception:
            pass
        page.wait_for_timeout(250)
    return False


def _have_playwright():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False
HAVE = _have_playwright()
BLANK = solid_png(64, 64, (186, 218, 245, 255))
# Every host the page might call. Chromium is pointed at a local TLS stub, so a service-worker
# fetch cannot leave the machine (Playwright's route does not see those fetches).
STUB_HOSTS = (
    'tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com', 'tiles.openfreemap.org', 'helpmap.uk', 'www.helpmap.uk',
    'api.postcodes.io', 'static.cloudflareinsights.com', 'cloudflareinsights.com', 'formsubmit.co')


class OfflineOsmTiles(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs playwright chromium')
    def test_offline_after_first_visit_shows_cached_osm_tiles(self):
        from playwright.sync_api import sync_playwright
        sw_text = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        override = {'body': None}
        phase = {'offline': False}
        offline_tiles = []
        asked = []

        class Site(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=R, **k)
            def log_message(self, fmt, *a):
                pass
            def do_GET(self):
                if urlparse(self.path).path == '/sw.js':
                    data = (override['body'] if override['body'] is not None else sw_text).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/javascript')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                super().do_GET()

        class Tiles(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *a):
                pass
            def do_GET(self):
                host = (self.headers.get('Host') or '').split(':')[0].lower()
                asked.append(host)
                if phase['offline']:
                    offline_tiles.append(host + ' ' + self.path)
                tile = host.endswith('openstreetmap.org') or host.endswith('maptiler.com') or host.endswith('stadiamaps.com')
                if tile:
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', str(len(BLANK)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=300')
                    self.end_headers()
                    self.wfile.write(BLANK)
                    return
                self.send_response(403)
                self.send_header('Content-Length', '0')
                self.end_headers()

        certs = tempfile.mkdtemp()
        subprocess.check_call(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', os.path.join(certs, 'key.pem'),
                               '-out', os.path.join(certs, 'cert.pem'), '-days', '1', '-nodes', '-subj', '/CN=tile.openstreetmap.org'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx_ssl.load_cert_chain(os.path.join(certs, 'cert.pem'), os.path.join(certs, 'key.pem'))
        tiles = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Tiles)
        tiles.socket = ctx_ssl.wrap_socket(tiles.socket, server_side=True)
        site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Site)
        threading.Thread(target=tiles.serve_forever, daemon=True).start()
        threading.Thread(target=site.serve_forever, daemon=True).start()
        rules = ', '.join('MAP %s 127.0.0.1:%d' % (host, tiles.server_address[1]) for host in STUB_HOSTS)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(args=['--host-rules=' + rules, '--ignore-certificate-errors'])
                ctx = browser.new_context(viewport={'width': 1280, 'height': 800}, service_workers='allow',
                                           user_agent='Mozilla/5.0 helpmap-check')
                page = ctx.new_page()
                page.goto('http://127.0.0.1:%d/?nocount' % site.server_address[1], wait_until='domcontentloaded')
                self.assertTrue(until(page, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)"),
                                'service worker did not take control')
                page.reload(wait_until='domcontentloaded')
                self.assertTrue(until(page, """() => window.TILE_ACTIVE === 'osm'
                       && [...document.querySelectorAll('#map .leaflet-tile-loaded')]
                            .filter(img => (img.getAttribute('data-tile')||img.src).includes('tile.openstreetmap.org') && img.naturalWidth > 0).length >= 4"""),
                                'online visit did not paint OpenStreetMap tiles')
                cached = page.evaluate("""async () => {
                    const c = await caches.open('fyfb-tiles2');
                    return (await c.keys()).map(r => r.url);
                }""")
                self.assertTrue(any('tile.openstreetmap.org' in u for u in cached), cached[:8])
                self.assertFalse(any('maptiler.com' in u for u in cached), cached)
                seeded = page.evaluate("""async () => {
                    const c = await caches.open('fyfb-tiles2');
                    await c.put('https://api.maptiler.com/maps/streets-v2/256/1/0/0.png',
                                new Response(new Uint8Array([137, 80, 78, 71]), {headers: {'content-type': 'image/png'}}));
                    return (await c.keys()).some(r => r.url.includes('maptiler.com'));
                }""")
                self.assertTrue(seeded)
                override['body'] = sw_text.replace("const C='fyfb-v96'", "const C='fyfb-v97'", 1)
                bumped = page.evaluate("""async () => {
                    const reg = await navigator.serviceWorker.getRegistration();
                    const done = new Promise(resolve => {
                        navigator.serviceWorker.addEventListener('controllerchange', () => resolve(navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL), {once: true});
                        setTimeout(() => resolve(''), 15000);
                    });
                    await reg.update();
                    return await done;
                }""")
                self.assertTrue(bumped, 'service worker did not take the version bump')
                self.assertTrue(until(page, """async () => {
                    const c = await caches.open('fyfb-tiles2');
                    const urls = (await c.keys()).map(r => r.url);
                    return urls.some(u => u.includes('tile.openstreetmap.org')) && !urls.some(u => u.includes('maptiler.com'));
                }""", secs=8), 'version bump left a MapTiler tile in the cache')
                phase['offline'] = True
                ctx.set_offline(True)
                page.reload(wait_until='domcontentloaded')
                self.assertTrue(until(page, """() => window.TILE_ACTIVE === 'osm'
                       && [...document.querySelectorAll('#map .leaflet-tile-loaded')]
                            .filter(img => (img.getAttribute('data-tile')||img.src).includes('tile.openstreetmap.org') && img.naturalWidth > 0).length >= 4"""),
                                'offline visit did not show cached OpenStreetMap tiles')
                shown = page.evaluate("""() => ({
                    active: window.TILE_ACTIVE,
                    tiles: [...document.querySelectorAll('#map .leaflet-tile-loaded')].filter(img => img.naturalWidth > 0).length,
                    osm: [...document.querySelectorAll('#map .leaflet-tile')].filter(img => (img.getAttribute('data-tile')||img.src).includes('tile.openstreetmap.org')).length,
                    credit: (document.querySelector('.leaflet-control-attribution') || {}).innerText || '',
                    logo: !!document.querySelector('.maptiler-logo')
                })""")
                self.assertEqual(shown['active'], 'osm', shown)
                self.assertGreaterEqual(shown['tiles'], 4, shown)
                self.assertGreaterEqual(shown['osm'], 4, shown)
                self.assertIn('OpenStreetMap', shown['credit'])
                self.assertFalse(shown['logo'])
                self.assertEqual(offline_tiles, [])
                self.assertNotIn('helpmap.uk', asked)
                self.assertTrue(any(h == 'tile.openstreetmap.org' for h in asked), asked)
                os.makedirs('/tmp/osm-default-shots', exist_ok=True)
                page.locator('#map').screenshot(path='/tmp/osm-default-shots/offline_cached_osm_tiles.png')
                browser.close()
        finally:
            site.shutdown()
            tiles.shutdown()
            shutil.rmtree(certs, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
