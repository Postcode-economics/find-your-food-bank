"""Every generated page has title, description, canonical, og:* and twitter:* tags (25 Oct 2026)."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
import beacon
NEED = ['<title>', 'name="description"', 'rel="canonical"', 'property="og:type"', 'property="og:title"', 'property="og:description"', 'property="og:url"',
        'property="og:image"', 'property="og:image:alt"', 'property="og:image:width"', 'property="og:image:height"', 'property="og:locale"',
        'name="twitter:card"', 'name="twitter:title"', 'name="twitter:description"', 'name="twitter:image"']
class T(unittest.TestCase):
    def test_every_page(self):
        bad = []
        for p in beacon.pages(R):
            rel = os.path.relpath(p, R); head = open(p, encoding='utf-8').read().split('</head>')[0]
            miss = [n for n in NEED if n not in head and not (rel == '404.html' and n == 'rel="canonical"')]  # 404 is noindex: no canonical
            if miss: bad.append((rel, miss))
        self.assertEqual(bad[:10], [])
if __name__ == '__main__': unittest.main()
