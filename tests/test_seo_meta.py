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
        self.assertIn('>Updated on 23 October at 13:29</a>', home)
        ds = [x for x in blocks(home) if x.get('@type') == 'Dataset'][0]
        self.assertEqual(ds['creator']['name'], 'Postcode Economics'); self.assertNotRegex(json.dumps(ds), r'\b0\d{9,10}\b')
        emails = set(re.findall(r'[\w.+-]+@[\w.-]+', json.dumps(ds))); self.assertEqual(emails, {'hello@helpmap.uk'})
        fq = [x for x in blocks(open(os.path.join(self.d, 'faq.html')).read()) if x.get('@type') == 'FAQPage'][0]
        self.assertGreaterEqual(len(fq['mainEntity']), 7)
        sm = open(os.path.join(self.d, 'sitemap.xml')).read()
        self.assertEqual(sm.count('<lastmod>2026-10-23</lastmod>'), len(ps)); self.assertIn('/faq.html', sm)
