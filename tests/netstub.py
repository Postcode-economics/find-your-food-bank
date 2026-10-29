"""Network-level stand-in for the iPhone WebKit map tests (no real network).

Why: Playwright's context.route() does not see requests made by a service worker in WebKit. With
service_workers='allow', sw.js fetched OpenStreetMap tiles past the test's route block, so a
'backup map on' run sometimes loaded OSM and never really forced the OpenFreeMap backup.

This module blocks at the network layer instead. The browser context is pointed at a local HTTP
proxy (Playwright's proxy option), so every request - page, worker or service worker - goes through it:
  helpmap.uk                -> this checkout, served over local TLS
  tiles.openfreemap.org     -> the stand-in OpenFreeMap style (other paths 404)
  api.postcodes.io          -> a stand-in answer
  tile.openstreetmap.org    -> the stand-in tile, or REFUSED when osm=False (the backup is forced)
  anything else             -> refused
Every CONNECT is logged in Stub.seen so a test can prove the block held.
Use the context with ignore_https_errors=True (the local certificate is self-signed).
tile_png may be a function of the tile path (a different tile per z/x/y); every OSM tile path served is logged in
Stub.tile_paths. tile_latency (seconds) and tile_headers make the stand-in answer like the real tile server.
"""
import json, mimetypes, os, select, socket, ssl, subprocess, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingTCPServer, StreamRequestHandler

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OSM = 'tile.openstreetmap.org'
HOSTS = ('helpmap.uk', 'tiles.openfreemap.org', 'api.postcodes.io', OSM)


def _cert(d):
    key, crt = os.path.join(d, 'k.pem'), os.path.join(d, 'c.pem')
    san = ','.join('DNS:' + h for h in HOSTS + ('*.' + OSM,))
    subprocess.check_call(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=helpmap.uk',
                           '-addext', 'subjectAltName=' + san, '-keyout', key, '-out', crt],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return crt, key


class Stub:
    def __init__(self, ofm_style, tile_png, postcode=None, osm=True, root=R, tile_latency=0, tile_headers=None):
        self.ofm_style, self.tile_png, self.postcode, self.osm, self.root = ofm_style, tile_png, postcode, osm, root
        self.tile_latency, self.tile_headers = tile_latency, dict(tile_headers or {})
        self.seen, self.refused, self.served, self.tile_paths = [], [], {'osm': 0, 'ofm': 0}, []
        self._lock = threading.Lock()

    # --- local TLS origin for every allowed host ---
    def _origin(self):
        stub = self

        class H(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def send(self, code, body=b'', ctype='text/plain', extra=None):
                self.send_response(code)
                self.send_header('content-type', ctype)
                self.send_header('content-length', str(len(body)))
                self.send_header('access-control-allow-origin', '*')
                if 'cache-control' not in {k.lower() for k in (extra or {})}:
                    self.send_header('cache-control', 'no-store')
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                host = (self.headers.get('host') or '').split(':')[0].lower()
                path = self.path.split('?')[0].split('#')[0] or '/'
                if host == 'helpmap.uk':
                    f = os.path.join(stub.root, path.lstrip('/'))
                    f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
                    if not os.path.isfile(os.path.realpath(f)):
                        return self.send(404)
                    with open(f, 'rb') as fh:
                        return self.send(200, fh.read(), mimetypes.guess_type(f)[0] or 'text/html')
                if host == 'tiles.openfreemap.org':
                    if path.startswith('/styles/'):
                        with stub._lock:
                            stub.served['ofm'] += 1
                        return self.send(200, stub.ofm_style.encode(), 'application/json')
                    return self.send(404)
                if host == 'api.postcodes.io' and stub.postcode is not None:
                    return self.send(200, json.dumps(stub.postcode).encode(), 'application/json')
                if host.endswith(OSM) and stub.osm:
                    with stub._lock:
                        stub.served['osm'] += 1
                        stub.tile_paths.append(path)
                    if stub.tile_latency:
                        time.sleep(stub.tile_latency)
                    body = stub.tile_png(path) if callable(stub.tile_png) else stub.tile_png
                    return self.send(200, body, 'image/png', dict({'x-helpmap-tile': 'stub'}, **stub.tile_headers))
                return self.send(404)

            def do_OPTIONS(self):
                self.send_response(204)
                for k, v in (('access-control-allow-origin', '*'), ('access-control-allow-headers', '*'),
                             ('access-control-allow-methods', 'GET, HEAD'), ('content-length', '0')):
                    self.send_header(k, v)
                self.end_headers()

        srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        srv.daemon_threads = True
        srv.handle_error = lambda *a: None  # browser closing a connection mid-reply is normal
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*self._certs)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        return srv

    # --- forward proxy: the only way out of the browser ---
    def _proxy(self):
        stub = self

        class P(StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline().decode('latin-1').strip()
                while self.rfile.readline() not in (b'\r\n', b'\n', b''):
                    pass
                parts = line.split()
                if len(parts) < 2:
                    return
                method, target = parts[0], parts[1]
                host = target.split('://')[-1].split('/')[0].split(':')[0].lower()
                ok = host in ('helpmap.uk', 'tiles.openfreemap.org', 'api.postcodes.io') or (host.endswith(OSM) and stub.osm)
                with stub._lock:
                    stub.seen.append(host)
                    if not ok:
                        stub.refused.append(host)
                if not ok or method != 'CONNECT':
                    self.wfile.write(b'HTTP/1.1 403 Forbidden\r\ncontent-length: 0\r\nconnection: close\r\n\r\n')
                    return
                up = socket.create_connection(('127.0.0.1', stub.origin.server_address[1]))
                self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
                self.wfile.flush()
                a = self.connection
                try:
                    while True:
                        r, _, _ = select.select([a, up], [], [], 30)
                        if not r:
                            break
                        for s in r:
                            data = s.recv(65536)
                            if not data:
                                return
                            (up if s is a else a).sendall(data)
                except OSError:
                    pass
                finally:
                    up.close()

        srv = ThreadingTCPServer(('127.0.0.1', 0), P)
        srv.daemon_threads = True
        return srv

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._certs = _cert(self._tmp.name)
        self.origin, self.proxy = self._origin(), self._proxy()
        for s in (self.origin, self.proxy):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        for s in (self.proxy, self.origin):
            s.shutdown()
            s.server_close()
        self._tmp.cleanup()

    def context_options(self):
        return {'proxy': {'server': 'http://127.0.0.1:%d' % self.proxy.server_address[1]}, 'ignore_https_errors': True}

    def osm_refused(self):
        with self._lock:
            return sum(1 for h in self.refused if h.endswith(OSM))
