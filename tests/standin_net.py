"""Local stand-in for tile hosts and, on iPhone WebKit, for https://helpmap.uk.

Fallback and backup checks inject failure here (HTTP 403, 429, 500, 404, or a dropped
connection). They do not call Playwright route() on a vector style or tilejson URL: with
the service worker blocked, that route answers 200 image/png and MapLibre stays grey.
The service worker is allowed, and it still reaches this server, because the failure is a
real response rather than a route().

Nothing in this process opens a socket to a public host.
"""
import mimetypes, os, socket, ssl, subprocess, tempfile, threading

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PNG = open(os.path.join(ROOT, 'scripts', 'tile_placeholder.png'), 'rb').read()
# Hosts a page may ask for. The certificate covers these. Unknown hosts get 403 and are recorded.
HOSTS = (
    'helpmap.uk', 'www.helpmap.uk',
    'tile.openstreetmap.org', 'a.tile.openstreetmap.org', 'b.tile.openstreetmap.org', 'c.tile.openstreetmap.org',
    'tiles.openfreemap.org', 'api.maptiler.com', 'tiles.stadiamaps.com',
    'basemaps.cartocdn.com', 'server.arcgisonline.com',
    'api.postcodes.io', 'static.cloudflareinsights.com', 'cloudflareinsights.com', 'formsubmit.co',
)
OFM_STYLE = (
    '{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
    '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
    '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
    '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}'
)


def _http(status, reason, body, ctype, headers):
    extra = ''.join('%s: %s\r\n' % (k, v) for k, v in headers.items())
    head = ('HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n%sConnection: close\r\n\r\n'
            ) % (status, reason, ctype, len(body), extra)
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


def _path_of(raw):
    line = raw.split(b'\r\n', 1)[0].decode('latin1', 'replace')
    parts = line.split(' ')
    return (parts[1] if len(parts) > 1 else '/').split('?', 1)[0]


class StandIn:
    """Decides the bytes for one host + path. None means drop the connection (no HTTP status)."""

    def __init__(self, root=None, style=None):
        self.root = os.path.abspath(root or ROOT)
        self.style = style if style is not None else OFM_STYLE
        self.lock = threading.Lock()
        self.decide = None  # callable(host, path) -> tuple or None; None falls through to default
        self.other = []
        self.errors = []
        self.sw_body = None  # bytes for /sw.js, or None to serve the file on disk
        self.missing = ()  # exact paths that return 404 (a library that failed to load)
        self.offline = False
        self._tls = None
        self._cert_dir = None
        self.tls_port = None
        self._tls_sock = None
        self._proxy = None

    def stop(self):
        for sock in (self._tls_sock, getattr(self._proxy, '_sock', None)):
            if sock is None:
                continue
            try:
                sock.close()
            except OSError:
                pass
        self._tls_sock = None

    def png(self, status=200, body=None, stub=False, cache=None):
        if cache is None:
            cache = 'public, max-age=86400' if status == 200 else 'no-store'
        headers = {'Access-Control-Allow-Origin': '*', 'Cache-Control': cache}
        if stub:
            headers['x-helpmap-tile'] = 'stub'
        return (status, 'image/png', PNG if body is None else body, headers)

    def json_style(self):
        raw = self.style.encode() if isinstance(self.style, str) else self.style
        return (200, 'application/json', raw, {'Access-Control-Allow-Origin': '*'})

    def empty(self, status):
        return (status, 'text/plain', b'', {'Access-Control-Allow-Origin': '*'})

    def json_body(self, body):
        raw = body if isinstance(body, bytes) else body.encode()
        return (200, 'application/json', raw, {'Access-Control-Allow-Origin': '*'})

    def site_file(self, path):
        rel = path.lstrip('/') or 'index.html'
        if rel.split('?', 1)[0] in self.missing or path in self.missing:
            return self.empty(404)
        if path == '/sw.js' and self.sw_body is not None:
            return (200, 'application/javascript', self.sw_body, {'Cache-Control': 'no-store'})
        f = os.path.normpath(os.path.join(self.root, rel))
        root = self.root
        if f != root and not f.startswith(root + os.sep):
            return self.empty(403)
        if os.path.isdir(f):
            f = os.path.join(f, 'index.html')
        if not os.path.isfile(f):
            return self.empty(404)
        ctype = mimetypes.guess_type(f)[0] or 'application/octet-stream'
        if f.endswith('.js'):
            ctype = 'application/javascript'
        return (200, ctype, open(f, 'rb').read(), {'Cache-Control': 'no-store'})

    def answer(self, host, path):
        host = (host or '').split(':')[0].lower()
        with self.lock:
            if self.offline:
                self.other.append('offline ' + host + path[:60])
                return None
            if self.decide is not None:
                return self.decide(host, path)
            return self.default(host, path)

    def default(self, host, path):
        if host == 'tile.openstreetmap.org' or host.endswith('.tile.openstreetmap.org'):
            return self.png(200, stub=True)
        if 'openfreemap.org' in host:
            low = path.lower()
            if '/styles/' in low or low.endswith('.json') or 'tilejson' in low:
                return self.json_style()
            return self.empty(404)
        if host in ('helpmap.uk', 'www.helpmap.uk'):
            return self.site_file(path)
        if host == 'api.postcodes.io':
            return self.empty(404)
        self.other.append(host + path[:80])
        return self.empty(403)

    def _cert(self):
        if self._tls is not None:
            return self._tls
        d = tempfile.mkdtemp(prefix='helpmap-standin-')
        self._cert_dir = d
        san = ','.join('DNS:' + h for h in HOSTS)
        subprocess.check_call(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', os.path.join(d, 'key.pem'),
             '-out', os.path.join(d, 'cert.pem'), '-days', '2', '-nodes', '-subj', '/CN=helpmap.uk',
             '-addext', 'subjectAltName=' + san],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.path.join(d, 'cert.pem'), os.path.join(d, 'key.pem'))
        try:
            ctx.set_alpn_protocols(['http/1.1'])
        except Exception:
            pass
        self._tls = ctx
        return ctx

    def host_rules(self):
        """Chromium --host-rules value. HTTPS tile hosts land on the local TLS server."""
        if not self.tls_port:
            self.serve_tls()
        mapped = [h for h in HOSTS if h not in ('helpmap.uk', 'www.helpmap.uk')]
        return ','.join('MAP %s 127.0.0.1:%d' % (h, self.tls_port) for h in mapped)

    def serve_tls(self):
        """Direct TLS server for Chromium --host-rules. The browser speaks TLS, no CONNECT."""
        if self._tls_sock is not None:
            return self.tls_port
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 0))
        sock.listen(80)
        self.tls_port = sock.getsockname()[1]
        self._tls_sock = sock
        threading.Thread(target=self._accept_tls, args=(sock,), daemon=True).start()
        return self.tls_port

    def _accept_tls(self, sock):
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            threading.Thread(target=self._tls_client, args=(conn,), daemon=True).start()

    def _tls_client(self, conn):
        try:
            conn.settimeout(20)
            tls = self._cert().wrap_socket(conn, server_side=True)
            req = _read_head(tls)
            if not req:
                return
            host = _header(req, 'host').split(':')[0]
            sent = self._send(tls, self.answer(host, _path_of(req)))
            if sent:
                tls.sendall(sent)
        except Exception as e:
            self._note(e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def serve_proxy(self):
        """HTTP proxy that answers CONNECT itself. WebKit iPhone checks use this."""
        if self._proxy is not None:
            return self._proxy
        self._proxy = Proxy(self)
        return self._proxy

    def _send(self, sock, decision):
        if decision is None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            return None
        status, ctype, body, headers = decision
        reason = {200: 'OK', 403: 'Forbidden', 404: 'Not Found', 429: 'Too Many Requests', 500: 'Error'}.get(status, 'OK')
        return _http(status, reason, body, ctype, headers)

    def _note(self, exc):
        name = type(exc).__name__
        if name not in ('SSLEOFError', 'ConnectionResetError', 'BrokenPipeError', 'timeout', 'SSLError'):
            self.errors.append('%s %s' % (name, str(exc)[:120]))


def _header(raw, name):
    want = name.lower()
    for line in raw.split(b'\r\n'):
        if b':' not in line:
            continue
        key, val = line.split(b':', 1)
        if key.decode('latin1', 'replace').lower() == want:
            return val.decode('latin1', 'replace').strip()
    return ''


class Proxy:
    def __init__(self, stand):
        self.stand = stand
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', 0))
        sock.listen(80)
        self.port = sock.getsockname()[1]
        self.url = 'http://127.0.0.1:%d' % self.port
        self._sock = sock
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
        stand = self.stand
        try:
            conn.settimeout(20)
            head = _read_head(conn)
            if not head:
                return
            first = head.split(b'\r\n', 1)[0].decode('latin1', 'replace')
            if not first.upper().startswith('CONNECT '):
                # Plain HTTP (the proxy itself). Not a tile host.
                host = _header(head, 'host')
                path = _path_of(head)
                sent = stand._send(conn, stand.answer(host, path))
                if sent:
                    conn.sendall(sent)
                return
            target = first.split(' ')[1]
            conn.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            tls = stand._cert().wrap_socket(conn, server_side=True)
            req = _read_head(tls)
            if not req:
                return
            host = target.split(':')[0].lower()
            sent = stand._send(tls, stand.answer(host, _path_of(req)))
            if sent:
                tls.sendall(sent)
        except Exception as e:
            stand._note(e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

