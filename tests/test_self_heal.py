"""Self-heal for stale HTML / old service workers (Instagram in-app browser, Dean 25 Oct 2026)."""
import os, re, json, unittest
R = os.path.join(os.path.dirname(__file__), '..'); rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()
class T(unittest.TestCase):
    def test_versions_in_sync(self):
        c = re.search(r"const C='([^']+)'", rd('sw.js')).group(1)
        self.assertEqual(json.loads(rd('version.json'))['build'], c, 'bump version.json with the sw cache name')
        self.assertIn('<meta name="helpmap-build" content="%s">' % c, rd('index.html'))
    def test_index_version_check(self):
        h = rd('index.html')
        for s in ("/version.json?t=", "cache:'no-store'", "unregister()", "caches.delete", "location.reload()", "sessionStorage.setItem(k,v.build)", 'http-equiv="Cache-Control" content="no-cache"'):
            self.assertIn(s, h)
        self.assertLess(h.index('helpmap-build'), h.index('</head>'))
    def test_sw_html_network_first_and_takeover(self):
        s = rd('sw.js')
        for x in ('self.skipWaiting()', 'self.clients.claim()', 'c.navigate(c.url)', "fetch(e.request.url,{cache:'no-cache'", 'version\\.json)$/'):
            self.assertIn(x, s)
        self.assertIn("updateViaCache:'none'", rd('layers.js'))
if __name__ == '__main__': unittest.main()

class Beacon(unittest.TestCase):
    def test_beacon_skips_automation(self):
        h = rd('index.html')
        self.assertNotIn("<script type='module' src='https://static.cloudflareinsights.com", h)
        for s in ('navigator.webdriver', 'HeadlessChrome', 'nocount', 'data-cf-beacon'): self.assertIn(s, h)
