"""Dean's standing rule (25 Oct 2026): DARK by default in Chromium AND WebKit, with the OS set to light, no preference or dark,
fresh visitor or storage blocked; only a saved light choice gives light. Runs scripts/dark_default.py against this checkout."""
import functools, http.server, os, sys, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
try:
    import playwright; HAVE = True
except Exception: HAVE = False
class T(unittest.TestCase):
    def test_wired_into_deploy_check(self):
        s = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml')).read(); self.assertIn('scripts/dark_default.py https://helpmap.uk', s)
    @unittest.skipUnless(HAVE, 'needs playwright')
    def test_dark_default_local(self):
        import dark_default
        # WebKit upgrades http subresources (CSP), so WebKit runs via the live-style route in test_webkit_instagram; here Chromium
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        try: bad = dark_default.run('http://127.0.0.1:%d' % s.server_address[1], ['chromium'])
        finally: s.shutdown()
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()
