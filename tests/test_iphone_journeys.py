"""WebKit journeys on iPhone 13 and iPhone SE.

These are the checks that would have caught the 27 Oct 2026 iPhone outage: a grey map after
OpenStreetMap starts returning 429 and the user taps Locate, a backup map that never paints,
a phone that stays grey offline, and a phone still on the fyfb-v90 worker that never paints
after the new worker arrives. A main-thread stall over one second fails on its own.

Both phones, service worker on and off where that is meaningful. Tiles are a stand-in served
by a local TLS proxy. Nothing is routed with Playwright's route(): on WebKit that interception
never delivers the response to the service-worker cache, so an offline check would be looking
at an empty cache. The proxy does not open a connection to any public host.

A grey map is a failure. Tests are not skipped and not marked expected-failure when the
current site still does this. The only skip is "Playwright's WebKit is not installed",
which is the plain pytest job. The iphone-journeys CI job installs WebKit and runs this file.

Paint means pixels, not a tile node in the DOM. A success tile is solid blue. The OpenFreeMap
stand-in draws solid green once its vector tile arrives. A refusal is a red body, so a 429
image on screen does not count as a painted map. The map must be painted within
GREY_TIMEOUT_S of the action. Longer than that is the grey screen.
"""
import mimetypes, os, socket, ssl, struct, subprocess, sys, tempfile, threading, traceback, unittest, zlib
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = 'https://helpmap.uk'
DEVICES = ('iPhone 13', 'iPhone SE')
GREY_TIMEOUT_S = 12
MAX_LONG_TASK_MS = 1000
V90 = 'e3982436c'  # fyfb-v90, the worker live phones still had
BLUE = (21, 101, 192)
GREEN = (46, 125, 50)
HERE = {'latitude': 51.5074, 'longitude': -0.1278}  # central London, not the default UK view
HOSTS = (
    'helpmap.uk', 'www.helpmap.uk', 'tile.openstreetmap.org', 'a.tile.openstreetmap.org',
    'b.tile.openstreetmap.org', 'c.tile.openstreetmap.org', 'tiles.openfreemap.org',
    'api.postcodes.io', 'static.cloudflareinsights.com', 'cloudflareinsights.com', 'formsubmit.co')
# Stand-in OpenFreeMap style. The land fill is drawn only from a vector tile, so a canvas
# with no tile request stays the grey background and fails the pixel check.
OFM_STYLE = (
    '{"version":8,"sources":{"uk":{"type":"vector","tiles":'
    '["https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf"],"minzoom":0,"maxzoom":14}},'
    '"layers":[{"id":"background","type":"background","paint":{"background-color":"#bdbdbd"}},'
    '{"id":"land","type":"fill","source":"uk","source-layer":"land","paint":{"fill-color":"#2e7d32"}}]}')
LONG_TASK = (
    "(() => { if (window.__lt) return; var lt = window.__lt = {max: 0, over: [], ticks: 0};"
    "lt.last = performance.now(); try { var o = new PerformanceObserver(function (list) {"
    "var es = list.getEntries(), i; for (i = 0; i < es.length; i++) { var e = es[i];"
    "if (e.duration > lt.max) lt.max = e.duration; if (e.duration > %d) lt.over.push(Math.round(e.duration)); } });"
    "o.observe({type: 'longtask', buffered: true}); lt.observer = true; } catch (err) { lt.observer = false; }"
    "setInterval(function () { var t = performance.now(), g = t - lt.last; lt.last = t; lt.ticks++;"
    "if (g > lt.max) lt.max = g; if (g > %d) lt.over.push(Math.round(g)); }, 50); })()"
) % (MAX_LONG_TASK_MS, MAX_LONG_TASK_MS)


def _webkit_installed():
    if os.environ.get('HELPMAP_JOURNEY_CHILD'):
        return True
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    base = os.path.expanduser('~/.cache/ms-playwright')
    return os.path.isdir(base) and any(name.startswith('webkit-') for name in os.listdir(base))


HAVE = _webkit_installed()


def _chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)


def solid_png(w, h, rgb):
    rgba = bytes(rgb) + b'\xff'
    raw = b''.join(b'\x00' + rgba * w for _ in range(h))
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + _chunk(b'IDAT', zlib.compress(raw, 9)) + _chunk(b'IEND', b''))


def _zz(n):
    return (n << 1) if n >= 0 else ((-n << 1) - 1)


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _field_bytes(field, blob):
    return _varint((field << 3) | 2) + _varint(len(blob)) + blob


def _field_varint(field, n):
    return _varint(field << 3) + _varint(n)


def land_pbf():
    """One polygon covering the tile, source-layer 'land'. MapLibre draws it green."""
    extent = 4096
    geom = bytearray()
    geom += _varint(1 | (1 << 3)) + _varint(_zz(0)) + _varint(_zz(0))
    geom += _varint(2 | (3 << 3))
    for dx, dy in ((extent, 0), (0, extent), (-extent, 0)):
        geom += _varint(_zz(dx)) + _varint(_zz(dy))
    geom += _varint(7 | (1 << 3))
    feat = _field_varint(3, 3) + _field_bytes(4, bytes(geom))
    layer = _field_bytes(1, b'land') + _field_bytes(2, feat) + _field_varint(5, extent) + _field_varint(15, 2)
    return _field_bytes(3, layer)


TILE_OK = solid_png(64, 64, BLUE)
TILE_REFUSED = solid_png(64, 64, (200, 30, 30))
PBF = land_pbf()


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def png_samples(png):
    """Grid of RGB samples from an 8-bit RGB or RGBA PNG. Used on map screenshots."""
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        raise AssertionError('screenshot is not a png')
    i, w, h, ctype, idat = 8, None, None, None, b''
    while i + 8 <= len(png):
        ln = struct.unpack('>I', png[i:i + 4])[0]
        tag, data = png[i + 4:i + 8], png[i + 8:i + 8 + ln]
        i += 12 + ln
        if tag == b'IHDR':
            w, h, bit, ctype = struct.unpack('>IIBB', data[:10])
            if bit != 8 or ctype not in (2, 6):
                raise AssertionError('unexpected png %s bit %s' % (ctype, bit))
        elif tag == b'IDAT':
            idat += data
        elif tag == b'IEND':
            break
    raw = zlib.decompress(idat)
    ch = 4 if ctype == 6 else 3
    stride, rows, pos, prev = w * ch, [], 0, bytearray(w * ch)
    for _ in range(h):
        filt, row = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for x in range(stride):
            left = row[x - ch] if x >= ch else 0
            up, ul = prev[x], prev[x - ch] if x >= ch else 0
            pred = (0, left, up, (left + up) // 2, _paeth(left, up, ul))[filt]
            row[x] = (row[x] + pred) & 255
        prev = row
        rows.append(row)
    pts = []
    for gy in range(1, 8):
        for gx in range(1, 8):
            x, y = int(w * gx / 8), int(h * gy / 8)
            o = x * ch
            pts.append((rows[y][o], rows[y][o + 1], rows[y][o + 2]))
    return pts


def _near(c, target, tol=28):
    return all(abs(a - b) <= tol for a, b in zip(c, target))


def classify(png):
    pts = png_samples(png)
    blue = sum(1 for c in pts if _near(c, BLUE))
    green = sum(1 for c in pts if _near(c, GREEN))
    n = len(pts) or 1
    kind = 'blue' if blue / n >= 0.30 else 'green' if green / n >= 0.30 else 'grey'
    return {'kind': kind, 'blue': blue, 'green': green, 'n': n, 'sample': pts[len(pts) // 2]}


def _http(status, reason, body, ctype, cache):
    head = ('HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n'
            'Access-Control-Allow-Origin: *\r\nCache-Control: %s\r\nConnection: close\r\n\r\n'
            ) % (status, reason, ctype, len(body), cache)
    return head.encode() + body


def _read_head(sock):
    data = b''
    while b'\r\n\r\n' not in data:
        part = sock.recv(16384)
        if not part:
            break
        data += part
        if len(data) > 262144:
            break
    return data


def _request_path(raw):
    line = raw.split(b'\r\n', 1)[0].decode('latin1', 'replace')
    parts = line.split(' ')
    return (parts[1] if len(parts) > 1 else '/').split('?', 1)[0]


class Proxy:
    """HTTP proxy that answers CONNECT itself. No socket is opened to the requested host."""

    def __init__(self):
        self.osm = 'ok'       # ok | refuse
        self.offline = False
        self.sw_body = None   # bytes served for /sw.js, or None for the file on disk
        self.hits = {'osm': 0, 'ofm_style': 0, 'ofm_pbf': 0}
        self.offline_hits = []
        self.other = []
        self.errors = []
        d = tempfile.mkdtemp(prefix='helpmap-journey-')
        san = ','.join('DNS:' + h for h in HOSTS)
        subprocess.check_call(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', os.path.join(d, 'key.pem'),
             '-out', os.path.join(d, 'cert.pem'), '-days', '2', '-nodes', '-subj', '/CN=helpmap.uk',
             '-addext', 'subjectAltName=' + san],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._tls.load_cert_chain(os.path.join(d, 'cert.pem'), os.path.join(d, 'key.pem'))
        try:
            self._tls.set_alpn_protocols(['http/1.1'])
        except Exception:
            pass
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(80)
        self.port = self._sock.getsockname()[1]
        self.url = 'http://127.0.0.1:%d' % self.port
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self):
        try:
            self._sock.close()
        except OSError:
            pass

    def _accept(self):
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        try:
            conn.settimeout(20)
            head = _read_head(conn)
            if not head:
                return
            first = head.split(b'\r\n', 1)[0].decode('latin1', 'replace')
            if not first.upper().startswith('CONNECT '):
                self.other.append(first[:80])
                return
            host = first.split(' ')[1]
            conn.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            tls = self._tls.wrap_socket(conn, server_side=True)
            req = _read_head(tls)
            if not req:
                return
            body = self._answer(host.split(':')[0].lower(), _request_path(req))
            if body:
                tls.sendall(body)
        except Exception as e:
            name = type(e).__name__
            if name not in ('SSLEOFError', 'ConnectionResetError', 'BrokenPipeError', 'timeout'):
                self.errors.append('%s %s' % (name, str(e)[:80]))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _answer(self, host, path):
        if self.offline:
            self.offline_hits.append(host + ' ' + path)
            return None
        if host == 'tile.openstreetmap.org' or host.endswith('.tile.openstreetmap.org'):
            self.hits['osm'] += 1
            if self.osm == 'refuse':
                return _http(429, 'Too Many Requests', TILE_REFUSED, 'image/png', 'no-store')
            return _http(200, 'OK', TILE_OK, 'image/png', 'public, max-age=86400')
        if host == 'tiles.openfreemap.org':
            if '/styles/' in path:
                self.hits['ofm_style'] += 1
                return _http(200, 'OK', OFM_STYLE.encode(), 'application/json', 'no-store')
            if path.endswith('.pbf'):
                self.hits['ofm_pbf'] += 1
                return _http(200, 'OK', PBF, 'application/x-protobuf', 'public, max-age=300')
            self.other.append(host + path[:60])
            return _http(404, 'Not Found', b'', 'text/plain', 'no-store')
        if host == 'api.postcodes.io':
            body = b'{"status":200,"result":{"postcode":"SW1A 1AA","latitude":51.501,"longitude":-0.141,"outcode":"SW1A"}}'
            return _http(200, 'OK', body, 'application/json', 'no-store')
        if host in ('helpmap.uk', 'www.helpmap.uk'):
            if path == '/sw.js' and self.sw_body is not None:
                return _http(200, 'OK', self.sw_body, 'application/javascript', 'no-store')
            rel = path.lstrip('/') or 'index.html'
            f = os.path.normpath(os.path.join(R, rel))
            if not f.startswith(os.path.abspath(R) + os.sep) and f != os.path.abspath(R):
                return _http(403, 'Forbidden', b'', 'text/plain', 'no-store')
            if os.path.isdir(f):
                f = os.path.join(f, 'index.html')
            if not os.path.isfile(f):
                return _http(404, 'Not Found', b'', 'text/plain', 'no-store')
            ctype = mimetypes.guess_type(f)[0] or 'application/octet-stream'
            if f.endswith('.js'):
                ctype = 'application/javascript'
            return _http(200, 'OK', open(f, 'rb').read(), ctype, 'no-store')
        self.other.append(host + path[:60])
        return _http(403, 'Forbidden', b'', 'text/plain', 'no-store')


def _until(pg, js, secs=20):
    last = None
    for _ in range(int(secs * 4)):
        try:
            last = pg.evaluate(js)
        except Exception as e:
            last = '%s' % e
        if last is True:
            return True
        pg.wait_for_timeout(250)
    return last


def _state(pg):
    try:
        return pg.evaluate("""() => ({active: window.TILE_ACTIVE || null, vector: window.TILE_VECTOR || null,
          failover: window.TILE_FAILOVER || null, imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length,
          canvas: !!document.querySelector('#map canvas')})""")
    except Exception as e:
        return {'error': str(e)[:160]}


def wait_paint(pg, proxy, want):
    """Poll the map screenshot until it is painted or GREY_TIMEOUT_S has passed. want is 'blue' or 'any'."""
    last = {'kind': 'grey', 'sample': None}
    ticks = max(1, int(GREY_TIMEOUT_S * 2))
    for _ in range(ticks):
        try:
            shot = pg.locator('#map').screenshot(timeout=5000)
            last = classify(shot)
            if last['kind'] == want or (want == 'any' and last['kind'] in ('blue', 'green')):
                return last
        except Exception as e:
            last = {'kind': 'grey', 'error': str(e)[:160], 'sample': None}
        pg.wait_for_timeout(500)
    detail = {'pixels': last, 'state': _state(pg), 'hits': dict(proxy.hits), 'other': proxy.other[:6],
              'proxy_errors': proxy.errors[:4]}
    raise AssertionError('map still %s after %ds (want %s): %s' % (last.get('kind'), GREY_TIMEOUT_S, want, detail))


def _context(p, browser, device, sw, proxy):
    dev = dict(p.devices[device])
    dev.pop('default_browser_type', None)
    ctx = browser.new_context(
        **dev, proxy={'server': proxy.url}, ignore_https_errors=True,
        service_workers='allow' if sw else 'block',
        geolocation=HERE, permissions=['geolocation'])
    ctx.add_init_script(LONG_TASK)
    return ctx


def _open(p, device, sw, proxy):
    browser = p.webkit.launch()
    ctx = _context(p, browser, device, sw, proxy)
    pg = ctx.new_page()
    pg.set_default_timeout(15000)
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)[:200]))
    pg.goto(BASE + '/?nocount', wait_until='domcontentloaded', timeout=30000)
    return browser, ctx, pg, errors


def _located(pg):
    got = _until(pg, "() => ((document.querySelector('#list .lh') || {}).textContent || '').indexOf('your location') >= 0", 8)
    if got is not True:
        raise AssertionError('Locate did not move the list to your location (%s) %s' % (got, _state(pg)))


def _long(pg):
    lt = pg.evaluate('() => window.__lt || null')
    if not lt or not lt.get('ticks'):
        raise AssertionError('long-task monitor did not run: %s' % lt)
    if (lt.get('max') or 0) > MAX_LONG_TASK_MS:
        raise AssertionError('main thread busy for %d ms (over %d): %s' % (lt['max'], MAX_LONG_TASK_MS, lt.get('over')))
    return lt['max']


def _check_quiet(proxy, errors):
    if proxy.other:
        raise AssertionError('request left the stand-in proxy: %s' % proxy.other[:6])
    # A page SyntaxError is part of the grey-map failure; surface it when the network leaked
    # or the caller includes `errors` in a paint failure. Unexpected hosts are the hard fail.
    return errors


def case_journey(device, sw):
    """First load paints, then Locate and Find nearest, and the map is still painted."""
    from playwright.sync_api import sync_playwright
    proxy = Proxy()
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            first = wait_paint(pg, proxy, 'blue')
            pg.locator('#me').tap()
            _located(pg)
            after_locate = wait_paint(pg, proxy, 'blue')
            pg.locator('#xnear').tap()
            _located(pg)
            after_near = wait_paint(pg, proxy, 'blue')
            _check_quiet(proxy, errors)
            print('OK journey', device, 'sw', int(sw), first['kind'], after_locate['kind'], after_near['kind'])
            browser.close()
    finally:
        proxy.stop()


def case_rate_limit(device, sw):
    """OSM answers, then 429. Locate must leave a painted map (backup or OSM) within the timeout."""
    from playwright.sync_api import sync_playwright
    proxy = Proxy()
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            wait_paint(pg, proxy, 'blue')
            proxy.osm = 'refuse'
            pg.locator('#me').tap()
            _located(pg)
            try:
                painted = wait_paint(pg, proxy, 'any')
            except AssertionError as e:
                raise AssertionError('429 then Locate left a grey map. %s pageerrors=%s' % (e, errors[:3]))
            _check_quiet(proxy, errors)
            print('OK 429', device, 'sw', int(sw), painted['kind'], 'pbf', proxy.hits['ofm_pbf'], 'vector', _state(pg).get('vector'))
            browser.close()
    finally:
        proxy.stop()


def case_backup(device, sw):
    """Every OSM tile is refused from the first request. The backup (or OSM) must paint."""
    from playwright.sync_api import sync_playwright
    proxy = Proxy()
    proxy.osm = 'refuse'
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            ready = _until(pg, "() => !!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))", 20)
            if ready is not True:
                raise AssertionError('map never built: %s %s' % (ready, errors[:3]))
            try:
                painted = wait_paint(pg, proxy, 'any')
            except AssertionError as e:
                raise AssertionError('forced backup stayed grey (sw %s). %s pageerrors=%s' % (sw, e, errors[:3]))
            _check_quiet(proxy, errors)
            print('OK backup', device, 'sw', int(sw), painted['kind'], 'pbf', proxy.hits['ofm_pbf'])
            browser.close()
    finally:
        proxy.stop()


def case_offline(device, sw):
    """After a first visit the service worker has the tiles. Offline, those tiles still paint."""
    if not sw:
        raise AssertionError('offline cache requires the service worker')
    from playwright.sync_api import sync_playwright
    proxy = Proxy()
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            controlled = _until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 20)
            if controlled is not True:
                raise AssertionError('service worker did not take control: %s %s' % (controlled, errors[:2]))
            pg.reload(wait_until='domcontentloaded')
            wait_paint(pg, proxy, 'blue')
            cached = _until(pg, """async () => {
              const keys = await caches.keys();
              for (const k of keys) {
                const c = await caches.open(k);
                if ((await c.keys()).some(r => r.url.indexOf('tile.openstreetmap.org') >= 0)) return true;
              }
              return false;
            }""", 10)
            if cached is not True:
                keys = pg.evaluate('async () => await caches.keys()')
                raise AssertionError('first visit did not cache an OpenStreetMap tile: %s' % keys)
            # The proxy stops answering. That is the network cut: Playwright's
            # context.set_offline makes WebKit throw "internal error" on reload
            # before the service worker can serve the cached page.
            proxy.offline = True
            before = len(proxy.offline_hits)
            pg.reload(wait_until='domcontentloaded')
            try:
                painted = wait_paint(pg, proxy, 'blue')
            except AssertionError as e:
                raise AssertionError('offline visit did not show cached tiles. %s offline_requests=%s' % (
                    e, proxy.offline_hits[before:before + 6]))
            _check_quiet(proxy, errors)
            print('OK offline', device, painted['kind'], 'blocked', len(proxy.offline_hits) - before)
            browser.close()
    finally:
        proxy.stop()


def case_v90(device, sw):
    """A phone controlled by the fyfb-v90 worker loads this build and the map paints."""
    if not sw:
        raise AssertionError('the v90 upgrade is a service-worker journey')
    from playwright.sync_api import sync_playwright
    old = subprocess.check_output(['git', 'show', V90 + ':sw.js'], cwd=R)
    proxy = Proxy()
    proxy.sw_body = old
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            controlled = _until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 25)
            if controlled is not True:
                raise AssertionError('v90 worker did not take control: %s %s proxy=%s' % (controlled, errors[:2], proxy.errors[:3]))
            active = _until(pg, "async () => { const r = await navigator.serviceWorker.getRegistration(); return !!(r && r.active && r.active.state === 'activated' && !r.installing && !r.waiting); }", 25)
            if active is not True:
                raise AssertionError('v90 worker did not activate: %s %s' % (active, errors[:2]))
            got = _until(pg, "async () => (await caches.keys()).indexOf('fyfb-v90') >= 0", 20)
            if got is not True:
                keys = pg.evaluate('async () => await caches.keys()')
                raise AssertionError('v90 worker did not install its cache: %s' % keys)
            proxy.sw_body = None  # this checkout's sw.js
            pg.goto(BASE + '/?nocount', wait_until='domcontentloaded')
            upgraded = _until(pg, """async () => {
              const k = await caches.keys();
              return k.indexOf('fyfb-v92') >= 0 && k.indexOf('fyfb-tiles2') >= 0 && k.indexOf('fyfb-v90') < 0 && k.indexOf('fyfb-tiles') < 0;
            }""", 25)
            if upgraded is not True:
                keys = pg.evaluate('async () => await caches.keys()')
                raise AssertionError('v90 worker did not upgrade: %s %s' % (keys, errors[:3]))
            pg.reload(wait_until='domcontentloaded')
            try:
                painted = wait_paint(pg, proxy, 'blue')
            except AssertionError as e:
                raise AssertionError('after the v90 upgrade the map did not paint. %s' % e)
            st = _state(pg)
            if st.get('active') not in (None, 'osm'):
                raise AssertionError('upgrade left the map on %s' % st)
            _check_quiet(proxy, errors)
            print('OK v90', device, painted['kind'], st.get('active'))
            browser.close()
    finally:
        proxy.stop()


def case_long_task(device, sw):
    """No main-thread gap over one second, including the backup switch that froze a phone."""
    from playwright.sync_api import sync_playwright
    proxy = Proxy()
    try:
        with sync_playwright() as p:
            browser, ctx, pg, errors = _open(p, device, sw, proxy)
            ready = _until(pg, "() => !!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))", 25)
            if ready is not True:
                raise AssertionError('map never built: %s' % ready)
            pg.wait_for_timeout(500)
            try:
                pg.locator('#me').tap()
                _located(pg)
            except Exception as e:
                raise AssertionError('Locate did not respond: %s' % e)
            proxy.osm = 'refuse'
            try:
                pg.locator('#me').tap()
            except Exception as e:
                raise AssertionError('second Locate did not respond: %s' % e)
            pg.wait_for_timeout(1500)
            gap = _long(pg)
            _check_quiet(proxy, errors)
            print('OK long-task', device, 'sw', int(sw), 'max', int(gap), 'ms')
            browser.close()
    finally:
        proxy.stop()


CASES = {
    'journey': case_journey,
    'rate429': case_rate_limit,
    'backup': case_backup,
    'offline': case_offline,
    'v90': case_v90,
    'longtask': case_long_task,
}


class Wiring(unittest.TestCase):
    """The suite is what CI runs. These do not need a browser."""

    def test_pixel_check_accepts_a_blue_tile_and_rejects_a_refusal(self):
        self.assertEqual(classify(TILE_OK)['kind'], 'blue')
        self.assertEqual(classify(solid_png(32, 32, GREEN))['kind'], 'green')
        self.assertEqual(classify(TILE_REFUSED)['kind'], 'grey')
        self.assertEqual(classify(solid_png(32, 32, (221, 221, 221)))['kind'], 'grey')  # leaflet background
        self.assertGreater(len(PBF), 16)

    def test_ci_runs_this_suite_without_skipping_or_xfail(self):
        yml = open(os.path.join(R, '.github', 'workflows', 'tests.yml'), encoding='utf-8').read()
        job = yml.split('\n  iphone-journeys:\n', 1)
        self.assertEqual(len(job), 2, 'iphone-journeys job missing from tests.yml')
        # The next job, if one is added later, is a two-space key. Step bodies are
        # indented four spaces, so a plain split on two spaces stops at the first step.
        import re
        m = re.search(r'\n  [A-Za-z0-9-]+:\n', job[1])
        body = job[1][:m.start()] if m else job[1]
        self.assertIn('tests/test_iphone_journeys.py', body)
        self.assertIn('playwright install --with-deps webkit', body)
        self.assertIn('fetch-depth: 0', body)
        self.assertIn("needs.changes.outputs.browser == '1'", yml.split('iphone-journeys:', 1)[1][:400])
        self.assertNotIn('xfail', body)
        self.assertNotIn('--ignore', body)
        src = open(os.path.abspath(__file__), encoding='utf-8').read()
        # The needles are split so this assertion does not match its own source line.
        for needle in ('@unittest.' + 'expectedFailure', 'pytest.mark.' + 'xfail',
                       'page.' + 'route(', 'context.' + 'route('):
            self.assertNotIn(needle, src)
        # The chromium offline check must be started by pytest itself, not hidden behind a chrome binary test.
        browser = yml.split('\n  browser-tests:\n', 1)[1].split('\n  design-lock:\n', 1)[0]
        self.assertNotIn('test -x /usr/bin/google-chrome &&', browser)
        self.assertIn('python -m pytest -q tests -rs', browser)

    def test_suite_is_not_dropped_by_the_changes_filter(self):
        """A pull request that only adds this file still sets the browser output, so the job runs."""
        yml = open(os.path.join(R, '.github', 'workflows', 'tests.yml'), encoding='utf-8').read()
        self.assertIn('tests/*.py)', yml)
        self.assertIn('grep -q playwright', yml)
        self.assertIn('playwright', open(os.path.abspath(__file__), encoding='utf-8').read())


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class IPhoneJourneys(unittest.TestCase):
    def _run(self, case, device, sw, limit):
        env = os.environ.copy()
        env['HELPMAP_JOURNEY_CHILD'] = '1'
        pr = subprocess.Popen(
            [sys.executable, '-u', os.path.abspath(__file__), case, device, '1' if sw else '0'],
            cwd=R, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = pr.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9)
            out, err = pr.communicate()
            self.fail('%s %s service-worker=%s froze (no result within %ds)\n%s\n%s' % (
                case, device, sw, limit, (out or '')[-1000:], (err or '')[-1000:]))
        if out:
            print(out.strip())
        self.assertEqual(pr.returncode, 0, '%s %s service-worker=%s failed\n%s%s' % (
            case, device, sw, (out or '')[-2000:], (err or '')[-2500:]))

    def test_first_load_locate_and_find_nearest_paint(self):
        for device in DEVICES:
            for sw in (False, True):
                with self.subTest(device=device, service_worker=sw):
                    self._run('journey', device, sw, 90)

    def test_osm_429_after_load_then_locate_paints(self):
        for device in DEVICES:
            for sw in (False, True):
                with self.subTest(device=device, service_worker=sw):
                    self._run('rate429', device, sw, 90)

    def test_forced_backup_paints_with_service_worker_on_and_off(self):
        for device in DEVICES:
            for sw in (False, True):
                with self.subTest(device=device, service_worker=sw):
                    self._run('backup', device, sw, 90)

    def test_offline_after_first_visit_shows_cached_tiles(self):
        for device in DEVICES:
            with self.subTest(device=device):
                self._run('offline', device, True, 120)

    def test_v90_service_worker_upgrades_and_paints(self):
        for device in DEVICES:
            with self.subTest(device=device):
                self._run('v90', device, True, 120)

    def test_no_long_task_over_one_second(self):
        for device in DEVICES:
            for sw in (False, True):
                with self.subTest(device=device, service_worker=sw):
                    self._run('longtask', device, sw, 90)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] in CASES:
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        try:
            CASES[sys.argv[1]](sys.argv[2], sys.argv[3] == '1')
        except Exception:
            traceback.print_exc()
            sys.exit(1)
    else:
        unittest.main()
