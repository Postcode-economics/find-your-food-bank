"""SW precache never drifts from index.html (25 Oct 2026: SHELL still listed cb20261025h after index moved to cb20261025i)."""
import os, re, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
import sw_version
class T(unittest.TestCase):
    def test_precache_matches_index(self):
        html = open(os.path.join(R, 'index.html'), encoding='utf-8').read(); sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        shell = re.findall(r"'([^']*)'", re.search(r"SHELL=\[([^\]]*)\]", sw).group(1))
        want = sw_version.wanted_versioned(html); self.assertTrue(want)
        self.assertEqual(sorted(x for x in shell if '?v=' in x), want)
        for x in shell: self.assertTrue(os.path.exists(os.path.join(R, x.split('?')[0])) or x == './', x)
    def test_sync_wired(self):
        self.assertIn('sync_precache(root, h2)', open(os.path.join(R, 'scripts', 'sw_version.py')).read())
if __name__ == '__main__': unittest.main()
