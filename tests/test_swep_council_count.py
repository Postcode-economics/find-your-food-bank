"""3 Nov: the SWEP council count is distinct councils (a council's extra pages not counted twice), equals sweep_sources.json, and the hand-written 382 wording matches it."""
import json, os, sys, tempfile, shutil, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import seo_meta

class T(unittest.TestCase):
    def test_count_matches_sweep_sources(self):
        counts = seo_meta.swep_counts(ROOT)
        n = counts["swep-councils"]
        self.assertEqual(n, len(json.load(open(os.path.join(ROOT, 'scripts', 'sweep_sources.json')))['councils']))
    def test_wording_matches_count(self):
        counts = seo_meta.swep_counts(ROOT)
        n = counts["swep-councils"]
        for f in ('index.html', os.path.join('scripts', 'seo_meta.py')):
            t = open(os.path.join(ROOT, f)).read()
            self.assertIn('all %d UK councils' % n, t, f)
        faq = open(os.path.join(ROOT, 'faq.html')).read()
        self.assertIn('<span data-n="swep-councils">%d</span>' % n, faq)
        import re
        self.assertEqual(set(re.findall(r'every UK council \((\d+)\)', faq)), {str(n)})

    def test_pages_count_ignores_stale_swep_status(self):
        """A stale logs/swep_status.json must not change the baked page count (12 Nov food-bank rebuild)."""
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "overrides"))
            os.makedirs(os.path.join(d, "scripts"))
            os.makedirs(os.path.join(d, "logs"))
            with open(os.path.join(d, "overrides", "swep_sources.json"), "w") as f:
                json.dump([
                    {"council": "A", "url": "https://example.test/a"},
                    {"council": "B", "url": "https://example.test/b"},
                    {"council": "C", "url": None},
                ], f)
            with open(os.path.join(d, "scripts", "sweep_sources.json"), "w") as f:
                json.dump({"councils": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}, f)
            with open(os.path.join(d, "logs", "swep_status.json"), "w") as f:
                json.dump({"sources": 99}, f)
            n = seo_meta.swep_counts(d)
            self.assertEqual(n["swep-pages"], 2)
            self.assertEqual(n["swep-councils"], 3)
        finally:
            shutil.rmtree(d)

if __name__ == '__main__': unittest.main()
