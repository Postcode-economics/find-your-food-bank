"""scripts/date_check.py blocks a publish. A stale layer stamp must fail; the real tree must pass."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import date_check
ROOT = os.path.join(os.path.dirname(__file__), '..')

def _site(root, sh_run, sh_label, page_label, data_day, page_run=None):
    os.makedirs(os.path.join(root, 'shelters', 'y'))
    os.makedirs(os.path.join(root, 'overrides'))
    stamp = {"run": "2026-10-26T05:55:03+00:00", "kind": "refresh", "label": "26 Oct 2026, 05:55",
             "layers": {"fb": {"run": "2026-10-26T05:55:03+00:00", "label": "26 Oct 2026, 05:55"},
                        "sh": {"run": sh_run, "label": sh_label},
                        "ws": {"run": "2026-10-26T05:32:27+00:00", "label": "26 Oct 2026, 05:32"}}}
    open(os.path.join(root, 'stamp.js'), 'w').write('window.FB_STAMP=' + json.dumps(stamp) + ';\n')
    open(os.path.join(root, 'data.js'), 'w').write('window.FB_DATA={"f":"%s","items":[]};' % data_day)
    open(os.path.join(root, 'shelters.js'), 'w').write('var SHELTERS={"updated":"%s","items":[]};' % data_day)
    open(os.path.join(root, 'warmspaces.js'), 'w').write('var WARMSPACES={"updated":"2026-10-26","items":[]};')
    mod = page_run or sh_run
    html = ('<html><head><script type="application/ld+json">{"@type": "WebPage", "dateModified": "%s"}</script></head>'
            '<body><footer><p>Information last updated %s.</p><p>Map data last checked %s</p></footer></body></html>' % (mod, page_label, page_label))
    open(os.path.join(root, 'shelters', 'y', 'index.html'), 'w').write(html)
    open(os.path.join(root, 'sitemap.xml'), 'w').write(
        '<?xml version="1.0"?><urlset><url><loc>https://helpmap.uk/shelters/y/</loc><lastmod>%s</lastmod></url></urlset>' % mod[:10])

class T(unittest.TestCase):
    def test_real_tree_passes(self):
        self.assertEqual(date_check.problems(ROOT), [])

    def test_stale_stamp_is_caught(self):
        """The 26 Oct failure: shelters.js says 26 Oct, stamp.js still says 25 Oct."""
        d = tempfile.mkdtemp()
        try:
            _site(d, '2026-10-25T05:19:45+00:00', '25 Oct 2026, 05:19', '25 Oct 2026, 05:19', '2026-10-26')
            bad = date_check.problems(d)
            self.assertTrue(any('sh: shown date 2026-10-25 is older than its data (2026-10-26)' in x for x in bad), bad)
        finally:
            shutil.rmtree(d)

    def test_page_that_drifts_from_its_stamp_is_caught(self):
        d = tempfile.mkdtemp()
        try:
            _site(d, '2026-10-26T05:34:43+00:00', '26 Oct 2026, 05:34', '25 Oct 2026, 05:19', '2026-10-26',
                  page_run='2026-10-25T05:19:45+00:00')
            bad = date_check.problems(d)
            self.assertTrue(any('shelters/y/index.html says' in x for x in bad), bad)
        finally:
            shutil.rmtree(d)

    def test_hard_coded_label_is_caught(self):
        d = tempfile.mkdtemp()
        try:
            _site(d, '2026-10-26T05:34:43+00:00', '25 Oct 2026, 05:19', '25 Oct 2026, 05:19', '2026-10-26')
            bad = date_check.problems(d)
            self.assertTrue(any('hard-coded' in x for x in bad), bad)
        finally:
            shutil.rmtree(d)

    def test_workflows_block_on_it(self):
        w = os.path.join(ROOT, '.github', 'workflows')
        for name in ('tests.yml', 'refresh.yml', 'refresh-shelters.yml', 'refresh-warmspaces.yml', 'sweep-daily.yml', 'deploy-check.yml'):
            self.assertIn('python scripts/date_check.py', open(os.path.join(w, name), encoding='utf-8').read(), name)
