"""Serve this checkout as https://helpmap.uk on 127.0.0.1:443 and [::1]:443, for CI browser jobs (stdlib + openssl).

Playwright's route() does not see a service worker's own fetches in WebKit, so with service_workers='allow' the
worker's precache went to the real helpmap.uk. Fetching a ?v= tag on the live site before it is deployed makes
Cloudflare store the old file under the new tag. With /etc/hosts pointing helpmap.uk at 127.0.0.1 and this server's
CA trusted by the runner, every request for helpmap.uk, page or worker, is answered from the checkout.

  sudo python3 scripts/local_helpmap.py CA_OUT.crt [PORT]   # writes the CA certificate, then serves until killed
"""
import mimetypes, os, socket, ssl, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

R = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
HOSTS = ('helpmap.uk', 'www.helpmap.uk')


def certs(d):
    run = lambda *a: subprocess.check_call(a, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ca_key, ca, key, csr, crt, ext = (os.path.join(d, n) for n in ('ca.key', 'ca.crt', 'k.pem', 'c.csr', 'c.pem', 'ext'))
    run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=helpmap CI local CA',
        '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        '-keyout', ca_key, '-out', ca)
    run('openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=helpmap.uk', '-keyout', key, '-out', csr)
    with open(ext, 'w') as f:
        f.write('subjectAltName=%s\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n' % ','.join('DNS:' + h for h in HOSTS))
    run('openssl', 'x509', '-req', '-in', csr, '-CA', ca, '-CAkey', ca_key, '-CAcreateserial', '-days', '2',
        '-extfile', ext, '-out', crt)
    return ca, crt, key


class Site(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def do_GET(self, head=False):
        path = unquote(urlsplit(self.path).path) or '/'
        f = os.path.realpath(os.path.join(R, path.lstrip('/')))
        if os.path.isdir(f):
            f = os.path.join(f, 'index.html')
        ok = f.startswith(R + os.sep) and os.path.isfile(f) and '/.git/' not in f
        body = open(f, 'rb').read() if ok else b'not found'
        self.send_response(200 if ok else 404)
        self.send_header('content-type', (mimetypes.guess_type(f)[0] or 'application/octet-stream') if ok else 'text/plain')
        self.send_header('content-length', str(len(body)))
        self.send_header('cache-control', 'no-store')
        self.send_header('access-control-allow-origin', '*')
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET(head=True)


def main(ca_out, port=443):
    ca, crt, key = certs(tempfile.mkdtemp())
    with open(ca, 'rb') as s, open(ca_out, 'wb') as d:
        d.write(s.read())
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)

    class TLS(ThreadingHTTPServer):
        daemon_threads = True

        def finish_request(self, request, addr):  # per-connection thread, so one stalled handshake blocks nobody
            request.settimeout(30)
            super().finish_request(ctx.wrap_socket(request, server_side=True), addr)

        def handle_error(self, request, addr):
            pass

    class TLS6(TLS):
        address_family = socket.AF_INET6

    v4 = TLS(('127.0.0.1', port), Site)
    try:
        threading.Thread(target=TLS6(('::1', port), Site).serve_forever, daemon=True).start()
    except OSError:
        pass  # no IPv6 loopback on this runner, so nothing can reach helpmap.uk over IPv6 either
    print('serving %s as https://helpmap.uk' % R, flush=True)
    v4.serve_forever()


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 443)
