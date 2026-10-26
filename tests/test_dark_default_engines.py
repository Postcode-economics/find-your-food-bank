"""Dean's standing rule (25 Oct 2026): DARK by default in Chromium AND WebKit, with the OS set to light, no preference or dark,
fresh visitor or storage blocked; only a saved light choice gives light. Runs scripts/dark_default.py against this checkout."""
import functools, http.server, os, sys, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
try:
    import playwright; HAVE = True
except Exception: HAVE = False
class T(unittest.TestCase):
    def test_wired_into_deploy_check(self):
        s = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml')).read()
        self.assertIn('scripts/dark_default.py https://helpmap.uk', s)
        self.assertIn('steps.darkdefault.outcome', s)  # its own step, named in the alert, not chained with &&
        self.assertNotIn('&& python scripts/dark_default.py', s)
        self.assertNotIn('-A "Mozilla/5.0 helpmap-check"', s)  # that agent is a challenge page, so version.json never matched
        self.assertIn('Chrome/129.0.6668.29 Mobile Safari/537.36 helpmap-check', s)
        src = open(os.path.join(R, 'scripts', 'dark_default.py'), encoding='utf-8').read()
        self.assertIn('check_browser', src)
        self.assertNotIn('HeadlessChrome', src)
        self.assertNotIn("sessionStorage.getItem('dd')", src)
        self.assertNotIn("wait_until='load'", src)
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertNotIn('xl3BtUpxQak69583G9Q6', tiles)  # rejected 26 Oct; an empty key is skipped
        self.assertIn("name: 'maptiler', key: ''", tiles)
        self.assertIn('tile.openstreetmap.org', tiles)
    def test_unstyled_page_does_not_pass(self):
        import dark_default  # colour check only; Playwright is imported inside run()
        for scheme_case in ('fresh', 'blocked', 'saved-dark', 'saved-light'):
            self.assertFalse(dark_default.ok_case(scheme_case, False, 'rgba(0, 0, 0, 0)'))
            self.assertFalse(dark_default.ok_case(scheme_case, False, 'rgb(0, 0, 0)'))
        self.assertTrue(dark_default.ok_case('fresh', False, 'rgb(10, 22, 40)'))
        self.assertTrue(dark_default.ok_case('saved-dark', False, 'rgb(10, 22, 40)'))
        self.assertTrue(dark_default.ok_case('blocked', False, 'rgb(10, 22, 40)'))
        self.assertTrue(dark_default.ok_case('saved-light', True, 'rgb(255, 255, 255)'))
        self.assertFalse(dark_default.ok_case('saved-light', False, 'rgb(10, 22, 40)'))
        self.assertFalse(dark_default.ok_case('fresh', True, 'rgb(255, 255, 255)'))
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
