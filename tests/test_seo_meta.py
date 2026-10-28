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
        for f in ('data.js', 'access.js'): shutil.copy(os.path.join(ROOT, f), self.d)
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
        # batch 4: data/stamp/access carry a content-hash stamp of their own bytes (cache-first safe)
        for f in ('data', 'stamp', 'access'):
            self.assertIn('<script src="%s.js?v=%s"></script>' % (f, SM.content_stamp(self.d, f + '.js')), home)
        self.assertNotIn('data.js?v=r', home)
        ds = [x for x in blocks(home) if x.get('@type') == 'Dataset'][0]
        self.assertEqual(ds['creator']['name'], 'Postcode Economics'); self.assertNotRegex(json.dumps(ds), r'\b0\d{9,10}\b')
        emails = set(re.findall(r'[\w.+-]+@[\w.-]+', json.dumps(ds))); self.assertEqual(emails, {'hello@helpmap.uk'})
        fq = [x for x in blocks(open(os.path.join(self.d, 'faq.html')).read()) if x.get('@type') == 'FAQPage'][0]
        self.assertGreaterEqual(len(fq['mainEntity']), 7)
        sm = open(os.path.join(self.d, 'sitemap.xml')).read()
        self.assertEqual(sm.count('<lastmod>2026-10-23</lastmod>'), len(ps)); self.assertIn('/faq.html', sm)

    def test_stamp_keeps_other_attributes(self):
        # batch 1 (#209) loads these as <script data-hm ... type="text/plain">; the content stamp must keep that form.
        p = os.path.join(self.d, 'index.html'); s = open(p).read()
        s = re.sub(r'<script src="(data|stamp|access)\.js\?v=[^"]*"></script>', r'<script data-hm src="\1.js?v=r20261001T0000" type="text/plain"></script>', s)
        open(p, 'w').write(s); SM.run(self.d); SM.run(self.d)
        home = open(p).read()
        for f in ('data', 'stamp', 'access'):
            self.assertEqual(home.count('<script data-hm src="%s.js?v=%s" type="text/plain"></script>' % (f, SM.content_stamp(self.d, f + '.js'))), 1, f)
        self.assertNotIn('?v=r20261001T0000', home)

    def test_map_checked_line(self):
        SM.run(self.d); SM.run(self.d)
        fq = open(os.path.join(self.d, 'faq.html')).read(); tw = open(os.path.join(self.d, 'food-banks', 'x', 'index.html')).read()
        self.assertEqual(fq.count('class="mapchk"'), 2); self.assertEqual(tw.count('class="mapchk"'), 1)
        self.assertIn('>Map data last checked 23 Oct 2026, 13:29</p>', fq)
        self.assertIn('lang="cy" data-run="2026-10-23T13:29:05+01:00">Gwiriwyd data’r map ddiwethaf 23 Hydref 2026, 13:29</p>', fq)
        self.assertIn('>Map data last checked 23 Oct 2026, 13:29</p><!--/mapchk--><p class="chk3">', tw)
        self.assertRegex(fq, r'<p class="upd">Last updated \d{1,2} \w{3} 20\d\d, \d\d:\d\d</p><!--mapchk-->')
        for s in (fq, tw):
            self.assertEqual(s.count('<script src="/stamp.js?v=r20261023T1329"></script>'), 1); self.assertEqual(s.count('<!--mapchkjs-->'), 1)
        home = open(os.path.join(self.d, 'index.html')).read(); self.assertNotIn('mapchk', home)
