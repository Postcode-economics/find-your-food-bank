"""The iphone-webkit CI job never reaches the live helpmap.uk (29 Oct 2026).

Playwright's route() does not see a WebKit service worker's own fetches, so the worker's precache in that job went
to the real site. It asked Cloudflare for layers.js?v=h48b3be38ff93 before #263 was deployed, and Cloudflare kept
the old layers.js under that tag, so Show more never appeared live. The job now resolves helpmap.uk to the runner
and serves this checkout there over TLS (scripts/local_helpmap.py), and stops before any test if that does not hold.
"""
import os, socket, ssl, subprocess, sys, tempfile, time, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rd = lambda *p: open(os.path.join(R, *p), encoding='utf-8').read()


def job(name):
    y = rd('.github', 'workflows', 'tests.yml')
    return y.split('\n  %s:\n' % name, 1)[1].split('\n  iphone-journeys:', 1)[0]


class Wiring(unittest.TestCase):
    def test_helpmap_resolves_to_the_runner_before_any_webkit_test(self):
        j = job('iphone-webkit')
        guard, tests = j.index('scripts/local_helpmap.py'), j.index('python -m pytest')
        self.assertLess(guard, tests)
        for k in ("127.0.0.1 helpmap.uk www.helpmap.uk", "::1 helpmap.uk www.helpmap.uk", "sudo tee -a /etc/hosts",
                  "update-ca-certificates", "getent ahosts helpmap.uk www.helpmap.uk",
                  '[ "$(curl -fsS https://helpmap.uk/version.json)" = "$(cat version.json)" ]'):
            self.assertIn(k, j[:tests])
        self.assertIn('exit 1', j[guard:tests])


class LocalSite(unittest.TestCase):
    def test_serves_the_checkout_as_helpmap_uk_over_tls(self):
        if subprocess.run(['which', 'openssl'], capture_output=True).returncode:
            self.skipTest('openssl not installed')
        d = tempfile.mkdtemp(); ca = os.path.join(d, 'ca.crt')
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
        pr = subprocess.Popen([sys.executable, os.path.join(R, 'scripts', 'local_helpmap.py'), ca, str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            ctx = None
            for _ in range(100):
                try:
                    if os.path.getsize(ca):
                        ctx = ssl.create_default_context(cafile=ca)
                        socket.create_connection(('127.0.0.1', port), 1).close()
                        break
                except OSError:
                    pass
                time.sleep(0.1)
            self.assertIsNotNone(ctx, 'local site did not start')

            def get(path):
                with socket.create_connection(('127.0.0.1', port), 5) as raw, \
                        ctx.wrap_socket(raw, server_hostname='helpmap.uk') as t:  # certificate checked for helpmap.uk
                    t.sendall(('GET %s HTTP/1.1\r\nHost: helpmap.uk\r\nConnection: close\r\n\r\n' % path).encode())
                    out = b''
                    while True:
                        b = t.recv(65536)
                        if not b: break
                        out += b
                head, _, body = out.partition(b'\r\n\r\n')
                return head.decode('latin-1'), body

            head, body = get('/layers.js?v=anything')
            self.assertIn('200', head.split('\r\n')[0])
            self.assertEqual(body, open(os.path.join(R, 'layers.js'), 'rb').read())
            self.assertIn('cache-control: no-store', head.lower())
            self.assertEqual(get('/')[1], open(os.path.join(R, 'index.html'), 'rb').read())
            self.assertIn('404', get('/../../etc/passwd')[0].split('\r\n')[0])
            self.assertIn('404', get('/.git/config')[0].split('\r\n')[0])
        finally:
            pr.kill(); pr.wait()


if __name__ == '__main__':
    unittest.main()
