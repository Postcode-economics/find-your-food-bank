"""Every page the site serves carries the helpmap.uk analytics beacon once, with the automated-check exclusion (25 Oct 2026)."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
import beacon
class T(unittest.TestCase):
    def test_every_page(self):
        ps = beacon.pages(R); self.assertGreater(len(ps), 500)
        bad = []
        for p in ps:
            t = open(p, encoding='utf-8').read()
            if t.count('data-cf-beacon') != 1 or beacon.TOKEN not in t or 'navigator.webdriver' not in t: bad.append(os.path.relpath(p, R))
        self.assertEqual(bad, [])
    def test_inject_idempotent(self):
        t = '<html><body>x</body></html>'; once = beacon.inject(t)
        self.assertEqual(beacon.inject(once), once); self.assertIn(beacon.TOKEN, once)
    def test_build_scripts_emit(self):
        self.assertIn('beacon.inject(text)', open(os.path.join(R, 'scripts', 'build_seo.py')).read())
        self.assertIn('beacon.inject_all(ROOT)', open(os.path.join(R, 'scripts', 'seo_meta.py')).read())
if __name__ == '__main__': unittest.main()
