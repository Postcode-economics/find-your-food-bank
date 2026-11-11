"""Sitemap lastmod is the date a page's meaningful content last changed."""
import datetime, json, os, re, shutil, sys, tempfile, unittest
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import sitemap_lastmod as SL
import seo_meta as SM

ROOT = os.path.join(os.path.dirname(__file__), '..')
NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


def parse_sm(path):
    tree = ET.parse(path)
    out = {}
    for url in tree.getroot():
        loc = url.find('sm:loc', NS).text
        lastmod = url.find('sm:lastmod', NS).text
        out[loc] = lastmod
    return out


PAGE = """<!doctype html><html><head><title>Food banks in X</title>
<script type="application/ld+json" data-ld="page">{"dateModified": "2026-11-11T15:10:47+00:00"}</script>
</head><body>
<h1>Food banks in X</h1>
<p>2 food banks listed.</p>
<ul class="s"><li><div class="n">Alpha Bank</div>
<div>1 High Street</div>
<p class="xrow"><b>Opening times:</b> Mon 10:00–12:00</p>
<p class="xrow"><b>Last checked:</b> 11 Nov 2026</p></li></ul>
<footer><p>Information last updated 11 Nov 2026, 15:10. Data: Give Food.</p></footer>
<!--mapchk--><p class="mapchk" data-run="2026-11-11T15:10:47+00:00">Map data last checked 11 Nov 2026, 15:10</p><!--/mapchk-->
<script src="/stamp.js?v=r20261111T1510"></script>
</body></html>"""


class HashIgnoresNoise(unittest.TestCase):
    def test_noise_does_not_change_hash(self):
        a = PAGE
        b = (PAGE
             .replace('11 Nov 2026, 15:10', '12 Nov 2026, 08:00')
             .replace('11 Nov 2026', '12 Nov 2026')
             .replace('2026-11-11T15:10:47+00:00', '2026-11-12T08:00:00+00:00')
             .replace('?v=r20261111T1510', '?v=r20261112T0800'))
        self.assertEqual(SL.meaningful_hash(a), SL.meaningful_hash(b))

    def test_real_content_changes_hash(self):
        changed = PAGE.replace('Mon 10:00–12:00', 'Mon 10:00–13:00')
        self.assertNotEqual(SL.meaningful_hash(PAGE), SL.meaningful_hash(changed))

    def test_added_listing_changes_hash(self):
        changed = PAGE.replace('</ul>', '<li><div class="n">Beta Bank</div></li></ul>')
        self.assertNotEqual(SL.meaningful_hash(PAGE), SL.meaningful_hash(changed))


class LastmodRules(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        os.makedirs(os.path.join(self.d, 'food-banks', 'x'))
        open(os.path.join(self.d, 'food-banks', 'x', 'index.html'), 'w').write(PAGE)
        open(os.path.join(self.d, 'index.html'), 'w').write('<html><body><a id="freshtxt">Updated 11 Nov 2026, 15:10</a><p>Hello</p></body></html>')
        self.rels = ['index.html', 'food-banks/x/index.html']
        self.today = datetime.date(2026, 11, 11)

    def test_new_urls_get_today(self):
        lastmods, store = SL.collect(self.d, self.rels, self.today, dates={}, bump=True)
        self.assertEqual(lastmods[SL.url_of('index.html')], '2026-11-11')
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-11-11')
        self.assertEqual(store[SL.url_of('food-banks/x/index.html')]['lastmod'], '2026-11-11')

    def test_unchanged_content_keeps_lastmod_when_day_moves(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        later = datetime.date(2026, 11, 18)
        lastmods, _ = SL.collect(self.d, self.rels, later, dates=dates, bump=True)
        self.assertEqual(lastmods[SL.url_of('index.html')], '2026-11-11')
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-11-11')

    def test_noise_only_change_does_not_bump(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        p = os.path.join(self.d, 'food-banks', 'x', 'index.html')
        open(p, 'w').write(PAGE.replace('Last checked:</b> 11 Nov 2026', 'Last checked:</b> 18 Nov 2026')
                               .replace('Information last updated 11 Nov 2026, 15:10.',
                                        'Information last updated 18 Nov 2026, 09:00.'))
        lastmods, _ = SL.collect(self.d, self.rels, datetime.date(2026, 11, 18), dates=dates, bump=True)
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-11-11')

    def test_real_change_bumps_only_that_url(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        p = os.path.join(self.d, 'food-banks', 'x', 'index.html')
        open(p, 'w').write(PAGE.replace('Mon 10:00–12:00', 'Mon 10:00–13:00'))
        lastmods, _ = SL.collect(self.d, self.rels, datetime.date(2026, 11, 18), dates=dates, bump=True)
        self.assertEqual(lastmods[SL.url_of('index.html')], '2026-11-11')
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-11-18')

    def test_fail_safe_keeps_previous_when_hash_unknown(self):
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
              '<url><loc>https://helpmap.uk/</loc><lastmod>2026-10-25</lastmod></url>',
              '<url><loc>https://helpmap.uk/food-banks/x/</loc><lastmod>2026-10-30</lastmod></url>',
              '</urlset>\n']
        open(os.path.join(self.d, 'sitemap.xml'), 'w').write('\n'.join(sm))
        lastmods, _ = SL.collect(self.d, self.rels, self.today, dates={}, bump=True)
        # No stored hash, so keep previous lastmod rather than stamping today.
        self.assertEqual(lastmods[SL.url_of('index.html')], '2026-10-25')
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-10-30')

    def test_build_seo_pass_does_not_bump(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        p = os.path.join(self.d, 'food-banks', 'x', 'index.html')
        open(p, 'w').write(PAGE.replace('Mon 10:00–12:00', 'Tue 09:00–11:00'))
        lastmods, store = SL.collect(self.d, self.rels, datetime.date(2026, 11, 18), dates=dates, bump=False)
        self.assertEqual(lastmods[SL.url_of('food-banks/x/index.html')], '2026-11-11')
        # seo_meta's later pass with bump=True does advance it
        lastmods2, _ = SL.collect(self.d, self.rels, datetime.date(2026, 11, 18), dates=dates, bump=True)
        self.assertEqual(lastmods2[SL.url_of('food-banks/x/index.html')], '2026-11-18')

    def test_store_has_no_private_or_listing_text(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        blob = json.dumps(dates[SL.STORE_KEY])
        self.assertNotIn('Alpha Bank', blob)
        self.assertNotIn('1 High Street', blob)
        self.assertNotIn('Last checked', blob)
        for url, rec in dates[SL.STORE_KEY].items():
            self.assertTrue(url.startswith('https://helpmap.uk'))
            self.assertEqual(set(rec), {'hash', 'lastmod'})
            self.assertRegex(rec['hash'], r'^[0-9a-f]{16}$')
            self.assertRegex(rec['lastmod'], r'^2026-11-11$')

    def test_written_sitemap_is_valid_xml_same_url_set(self):
        dates = {}
        SL.write_urlset(self.d, self.rels, self.today, dates=dates, bump=True, persist=True)
        got = parse_sm(os.path.join(self.d, 'sitemap.xml'))
        self.assertEqual(set(got), {SL.url_of(r) for r in self.rels})
        self.assertTrue(all(v == '2026-11-11' for v in got.values()))
        # deterministic
        SL.write_urlset(self.d, self.rels, datetime.date(2026, 11, 18), dates=dates, bump=True, persist=True)
        got2 = parse_sm(os.path.join(self.d, 'sitemap.xml'))
        self.assertEqual(got, got2)

    def test_corrupt_store_keeps_previous(self):
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n<url><loc>https://helpmap.uk/</loc><lastmod>2026-09-01</lastmod></url>\n</urlset>\n'
        open(os.path.join(self.d, 'sitemap.xml'), 'w').write(sm)
        dates = {SL.STORE_KEY: 'not-a-dict'}
        lastmods, store = SL.collect(self.d, ['index.html'], self.today, dates=dates, bump=True)
        self.assertEqual(lastmods[SL.url_of('index.html')], '2026-09-01')
        self.assertNotIn('not-a-dict', json.dumps(store))


class SeoMetaIntegration(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        for f in SM.TOP:
            shutil.copy(os.path.join(ROOT, f), self.d)
        os.makedirs(os.path.join(self.d, 'food-banks', 'x'))
        os.makedirs(os.path.join(self.d, 'overrides'))
        shutil.copy(os.path.join(ROOT, 'food-banks', 'sutton', 'index.html'),
                    os.path.join(self.d, 'food-banks', 'x', 'index.html'))
        for f in ('data.js', 'access.js'):
            shutil.copy(os.path.join(ROOT, f), self.d)
        open(os.path.join(self.d, 'stamp.js'), 'w').write(
            'window.FB_STAMP={"run": "2026-10-23T13:29:05+01:00", "kind": "refresh", "label": "x"};\n')

    def test_seo_meta_keeps_lastmod_across_later_refresh(self):
        ps = SM.run(self.d)
        first = parse_sm(os.path.join(self.d, 'sitemap.xml'))
        self.assertEqual(set(first), {SM.url_of(r) for r in ps})
        self.assertTrue(all(v == '2026-10-23' for v in first.values()))
        # A later refresh with the same pages must not stamp the new day.
        open(os.path.join(self.d, 'stamp.js'), 'w').write(
            'window.FB_STAMP={"run": "2026-11-11T15:10:47+00:00", "kind": "refresh", "label": "x"};\n')
        SM.run(self.d)
        second = parse_sm(os.path.join(self.d, 'sitemap.xml'))
        self.assertEqual(first, second)
        # Store lived in page_dates.json and contains only hashes and dates.
        dates = json.load(open(os.path.join(self.d, 'overrides', 'page_dates.json')))
        self.assertIn(SL.STORE_KEY, dates)
        blob = json.dumps(dates[SL.STORE_KEY])
        self.assertNotIn('@', blob)  # no emails
        self.assertTrue(all(k.startswith('https://helpmap.uk') for k in dates[SL.STORE_KEY]))
        # A real wording change on one page bumps only that lastmod.
        faq = os.path.join(self.d, 'faq.html')
        open(faq, 'a').write('\n<!-- unique-content-change -->\n')
        SM.run(self.d)
        third = parse_sm(os.path.join(self.d, 'sitemap.xml'))
        self.assertEqual(third[SM.url_of('faq.html')], '2026-11-11')
        for url, day in first.items():
            if url != SM.url_of('faq.html'):
                self.assertEqual(third[url], day, url)


if __name__ == '__main__':
    unittest.main()
