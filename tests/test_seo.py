import os, re, sys, json, tempfile, unittest, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import build_seo as B

class SeoPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp()
        cls.urls = B.build(out=cls.out, fetch=False)   # cached areas only, no network in tests
    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.out)
    def read(self, u): return open(os.path.join(self.out, u.lstrip('/'), 'index.html'), encoding='utf-8').read()
    def test_slug(self):
        self.assertEqual(B.slug('Brighton & Hove'), 'brighton-and-hove')
        self.assertEqual(B.slug("King's Lynn and West Norfolk"), 'king-s-lynn-and-west-norfolk')
    def test_pages_exist_and_indexes(self):
        if not os.path.exists(B.CACHE): self.skipTest('no district cache')
        self.assertIn('/food-banks/', self.urls); self.assertIn('/warm-spaces/', self.urls)
        self.assertGreater(len(self.urls), 50)
    def test_page_content(self):
        for u in self.urls[:40]:
            h = self.read(u)
            self.assertIn('<link rel="canonical" href="https://helpmap.uk%s">' % u, h)
            self.assertIn('cannot accept liability', h); self.assertIn('/privacy.html', h)
            self.assertEqual(h.count('<title>'), 1)
            for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h): json.loads(m.replace('<\\/', '</'))
            if u.count('/') == 3: self.assertIn('Open on the map</a>', h); self.assertIn('href="/?q=', h)
    def test_titles_unique(self):
        t = [re.search('<title>(.*?)</title>', self.read(u)).group(1) for u in self.urls]
        self.assertEqual(len(t), len(set(t)))
    def test_internal_links_resolve(self):
        ok = set(self.urls)
        for u in self.urls:
            for l in re.findall(r'href="(/(?:food-banks|warm-spaces)/[^"]*)"', self.read(u)): self.assertIn(l, ok, (u, l))
    def test_sitemap_robots_404(self):
        sm = open(os.path.join(self.out, 'sitemap.xml')).read()
        self.assertEqual(sm.count('<loc>'), len(self.urls) + 4); self.assertIn('<lastmod>', sm)
        self.assertIn('Sitemap: https://helpmap.uk/sitemap.xml', open(os.path.join(self.out, 'robots.txt')).read())
        self.assertIn('noindex', open(os.path.join(self.out, '404.html')).read())
    def test_no_owner_address(self):
        for f in ['sitemap.xml', 'robots.txt', '404.html'] + [u.lstrip('/') + 'index.html' for u in self.urls if u.count('/') == 2]:
            h = open(os.path.join(self.out, f), encoding='utf-8').read()
            self.assertNotIn('Siskin', h)
    def test_voucher_tag_matches_map(self):
        i = {'id': 'x', 'name': 'N', 'address': 'A', 'phone': '01234 567890', 'opening_times': {'status': 'TIMES_FOUND', 'structured': {'mon': [['10:00', '12:00']]}}}
        h = B.card_fb(i, {'x': 'voucher'})
        self.assertIn('Foodbank voucher needed', h); self.assertIn('tel:01234567890', h); self.assertIn('Mon', h)
        self.assertIn('Walk-in not confirmed', B.card_fb(i, {}))
        self.assertIn('Call for opening times', B.card_fb({'id': 'y', 'name': 'N'}, {}))

if __name__ == '__main__': unittest.main()
