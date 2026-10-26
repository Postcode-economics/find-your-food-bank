import json, os, re, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import seo_meta as SM
ROOT = os.path.join(os.path.dirname(__file__), '..')
def blocks(s): return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', s, re.S)]
class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        for f in SM.TOP: shutil.copy(os.path.join(ROOT, f), self.d)
        os.makedirs(os.path.join(self.d, 'food-banks', 'x'))
        shutil.copy(os.path.join(ROOT, 'food-banks', 'sutton', 'index.html'), os.path.join(self.d, 'food-banks', 'x'))
        open(os.path.join(self.d, 'stamp.js'), 'w').write('window.FB_STAMP={"run": "2026-10-23T13:29:05+01:00", "kind": "refresh", "label": "x"};\n')
    def tearDown(self): shutil.rmtree(self.d)
    def test_run(self):
        ps = SM.run(self.d); SM.run(self.d)   # idempotent
        for rel in ps:
            s = open(os.path.join(self.d, rel)).read(); b = blocks(s)
            pg = [x for x in b if x.get('@type') == 'WebPage']
            self.assertEqual(len(pg), 1, rel); self.assertEqual(pg[0]['dateModified'], '2026-10-23T13:29:05+01:00')
        home = open(os.path.join(self.d, 'index.html')).read()
        self.assertIn('>Updated 23 Oct 2026, 13:29</a>', home)
        self.assertIn('<script src="data.js?v=r20261023T1329"></script>', home); self.assertIn('stamp.js?v=r20261023T1329', home)
        ds = [x for x in blocks(home) if x.get('@type') == 'Dataset'][0]
        self.assertEqual(ds['creator']['name'], 'Postcode Economics'); self.assertNotRegex(json.dumps(ds), r'\b0\d{9,10}\b')
        emails = set(re.findall(r'[\w.+-]+@[\w.-]+', json.dumps(ds))); self.assertEqual(emails, {'hello@helpmap.uk'})
        fq = [x for x in blocks(open(os.path.join(self.d, 'faq.html')).read()) if x.get('@type') == 'FAQPage'][0]
        self.assertGreaterEqual(len(fq['mainEntity']), 7)
        sm = open(os.path.join(self.d, 'sitemap.xml')).read()
        self.assertEqual(sm.count('<lastmod>2026-10-23</lastmod>'), len(ps)); self.assertIn('/faq.html', sm)

    def test_map_checked_line(self):
        SM.run(self.d); SM.run(self.d)
        fq = open(os.path.join(self.d, 'faq.html')).read(); tw = open(os.path.join(self.d, 'food-banks', 'x', 'index.html')).read()
        self.assertEqual(fq.count('class="mapchk"'), 2); self.assertEqual(tw.count('class="mapchk"'), 1)
        self.assertIn('>Map data last checked 23 Oct 2026, 13:29</p>', fq)
        self.assertIn('lang="cy" data-run="2026-10-23T13:29:05+01:00">Gwiriwyd data’r map ddiwethaf 23 Oct 2026, 13:29</p>', fq)
        self.assertIn('>Map data last checked 23 Oct 2026, 13:29</p><!--/mapchk--><p class="chk3">', tw)
        self.assertRegex(fq, r'<p class="upd">Last updated \d{1,2} \w{3} 20\d\d, \d\d:\d\d</p><!--mapchk-->')
        for s in (fq, tw):
            self.assertEqual(s.count('<script src="/stamp.js?v=r20261023T1329"></script>'), 1); self.assertEqual(s.count('<!--mapchkjs-->'), 1)
        home = open(os.path.join(self.d, 'index.html')).read(); self.assertNotIn('mapchk', home)

    def test_each_page_uses_its_own_refresh(self):
        """A food bank publish must not restamp shelter pages, and a policy page keeps the day its text changed."""
        os.makedirs(os.path.join(self.d, 'shelters', 'y'))
        shutil.copy(os.path.join(self.d, 'food-banks', 'x', 'index.html'), os.path.join(self.d, 'shelters', 'y', 'index.html'))
        open(os.path.join(self.d, 'stamp.js'), 'w').write(
            'window.FB_STAMP={"run":"2026-10-26T05:55:03+00:00","kind":"refresh","label":"26 Oct 2026, 05:55",'
            '"layers":{"fb":{"run":"2026-10-26T05:55:03+00:00","label":"26 Oct 2026, 05:55"},'
            '"sh":{"run":"2026-10-25T05:19:45+00:00","label":"25 Oct 2026, 05:19"},'
            '"ws":{"run":"2026-10-26T05:32:27+00:00","label":"26 Oct 2026, 05:32"}}};\n')
        os.makedirs(os.path.join(self.d, 'overrides'))
        SM.run(self.d)
        dates = json.load(open(os.path.join(self.d, 'overrides', 'page_dates.json')))
        dates['privacy.html']['at'] = '2026-10-25T12:45:21+00:00'
        json.dump(dates, open(os.path.join(self.d, 'overrides', 'page_dates.json'), 'w'))
        SM.run(self.d)
        def modified(rel):
            s = open(os.path.join(self.d, rel), encoding='utf-8').read()
            return [x['dateModified'] for x in blocks(s) if x.get('@type') == 'WebPage'][0]
        self.assertEqual(modified('food-banks/x/index.html'), '2026-10-26T05:55:03+00:00')
        self.assertEqual(modified('shelters/y/index.html'), '2026-10-25T05:19:45+00:00')
        self.assertIn('Information last updated 25 Oct 2026, 05:19.', open(os.path.join(self.d, 'shelters', 'y', 'index.html'), encoding='utf-8').read())
        self.assertIn('Map data last checked 25 Oct 2026, 05:19', open(os.path.join(self.d, 'shelters', 'y', 'index.html'), encoding='utf-8').read())
        self.assertEqual(modified('privacy.html'), '2026-10-25T12:45:21+00:00')
        sm = open(os.path.join(self.d, 'sitemap.xml'), encoding='utf-8').read()
        self.assertIn('<loc>https://helpmap.uk/shelters/y/</loc><lastmod>2026-10-25</lastmod>', sm)
        self.assertIn('<loc>https://helpmap.uk/food-banks/x/</loc><lastmod>2026-10-26</lastmod>', sm)
        self.assertIn('<loc>https://helpmap.uk/privacy.html</loc><lastmod>2026-10-25</lastmod>', sm)
        self.assertNotIn('<loc>https://helpmap.uk/privacy.html</loc><lastmod>2026-10-26</lastmod>', sm)
        dates['faq.html']['at'] = '2026-10-25T12:45:21+00:00'
        json.dump(dates, open(os.path.join(self.d, 'overrides', 'page_dates.json'), 'w'))
        SM.run(self.d)
        fq = open(os.path.join(self.d, 'faq.html'), encoding='utf-8').read()
        self.assertEqual(modified('faq.html'), '2026-10-25T12:45:21+00:00')  # the page text, not the food-bank publish
        self.assertIn('Last updated 25 Oct 2026, 12:45', fq)
        self.assertIn('Map data last checked 26 Oct 2026, 05:55', fq)  # the data refresh
        sm = open(os.path.join(self.d, 'sitemap.xml'), encoding='utf-8').read()
        self.assertIn('<loc>https://helpmap.uk/faq.html</loc><lastmod>2026-10-25</lastmod>', sm)
