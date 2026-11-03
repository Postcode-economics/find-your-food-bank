"""3 Nov: the SWEP council count is distinct councils (a council's extra pages not counted twice), equals sweep_sources.json, and the hand-written 382 wording matches it."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import seo_meta

class T(unittest.TestCase):
    def test_count_matches_sweep_sources(self):
        n = seo_meta.swep_counts(ROOT)['swep-councils']
        self.assertEqual(n, len(json.load(open(os.path.join(ROOT, 'scripts', 'sweep_sources.json')))['councils']))
    def test_wording_matches_count(self):
        n = seo_meta.swep_counts(ROOT)['swep-councils']
        for f in ('index.html', os.path.join('scripts', 'seo_meta.py')):
            t = open(os.path.join(ROOT, f)).read()
            self.assertIn('all %d UK councils' % n, t, f)
        faq = open(os.path.join(ROOT, 'faq.html')).read()
        self.assertIn('<span data-n="swep-councils">%d</span>' % n, faq)
        import re
        self.assertEqual(set(re.findall(r'every UK council \((\d+)\)', faq)), {str(n)})

if __name__ == '__main__': unittest.main()
