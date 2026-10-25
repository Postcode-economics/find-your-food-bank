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

class SingleSource(unittest.TestCase):
    def test_sync_from_sw(self):
        import tempfile, shutil, sys
        sys.path.insert(0, os.path.join(R, 'scripts')); import sw_version
        d = tempfile.mkdtemp()
        for f in ('sw.js', 'index.html', 'version.json'): shutil.copy(os.path.join(R, f), d)
        s = open(os.path.join(d, 'sw.js')).read(); open(os.path.join(d, 'sw.js'), 'w').write(re.sub(r"const C='[^']+'", "const C='fyfb-v999'", s))
        self.assertEqual(sw_version.sync(d), 'fyfb-v999')
        self.assertEqual(json.load(open(os.path.join(d, 'version.json')))['build'], 'fyfb-v999')
        h = open(os.path.join(d, 'index.html')).read()
        self.assertIn('content="fyfb-v999"', h); self.assertIn("var b='fyfb-v999'", h); shutil.rmtree(d)
    def test_workflows_commit_version_json(self):
        wf = os.path.join(R, '.github', 'workflows')
        for f in ('refresh.yml', 'refresh-shelters.yml', 'refresh-warmspaces.yml', 'sweep-daily.yml'):
            self.assertIn('version.json', open(os.path.join(wf, f)).read(), f)
        self.assertIn('sw_version.sync()', rd('scripts/seo_meta.py'))

class BeaconToken(unittest.TestCase):
    def test_helpmap_token(self):
        """helpmap.uk Cloudflare Web Analytics token (supplied by Dean 25 Oct 2026)."""
        self.assertIn('{"token": "6a7058ad322d49b481a8849a493add24"}', rd('index.html'))
