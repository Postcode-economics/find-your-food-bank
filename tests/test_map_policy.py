"""Permanent map policy test (docs/MAP_POLICY.md, Dean 26 Oct 2026 17:12). Do not weaken."""
import json, os, re, subprocess, unittest

R = os.path.join(os.path.dirname(__file__), '..')
TILES = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()


def _eval(extra=''):
    js = 'var window = {};' + TILES + '\n' + extra + '\nprocess.stdout.write(JSON.stringify({all: window.TILE_PROVIDERS, cand: window.tileCandidates().map(function (p) { return p.name; })}))'
    return json.loads(subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True).stdout)


class MapPolicy(unittest.TestCase):
    def test_order_is_osm_then_openfreemap(self):
        d = _eval()
        names = [p['name'] for p in d['all']]
        self.assertEqual(names[:2], ['osm', 'openfreemap'])
        self.assertEqual(d['cand'], ['osm', 'openfreemap'])
        self.assertTrue(d['all'][0]['url'].startswith('https://tile.openstreetmap.org/'))
        ofm = d['all'][1]
        self.assertTrue(ofm['url'].startswith('https://tiles.openfreemap.org/styles/'))
        self.assertNotRegex(ofm['url'].lower(), r'dark|fiord')
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', ofm['attribution']).replace('&copy;', '©')).strip()
        self.assertEqual(text, 'OpenFreeMap © OpenMapTiles Data from OpenStreetMap')

    def test_no_stadia_anywhere_in_tiles_js(self):
        names = [p['name'].lower() for p in _eval()['all']]
        self.assertNotIn('stadia', names)
        self.assertNotIn('stadiamaps', TILES.lower())
        self.assertEqual([n for n in names if 'stadia' in n], [])

    def test_maptiler_absent_or_disabled(self):
        for p in _eval()['all']:
            if 'maptiler' in p['name'].lower() or 'maptiler' in p['url'].lower():
                self.assertIs(p.get('disabled'), True, p)
                self.assertFalse(p.get('key'), p)
        # Even with a key pasted in and the list reordered, MapTiler is never a candidate.
        d = _eval("window.TILE_PROVIDERS.forEach(function (p) { if (p.name === 'maptiler') p.key = 'x'; }); window.TILE_PROVIDERS.reverse();")
        self.assertEqual(d['cand'][0], 'osm')
        self.assertNotIn('maptiler', d['cand'])

    def test_policy_doc_present(self):
        doc = open(os.path.join(R, 'docs', 'MAP_POLICY.md'), encoding='utf-8').read()
        for s in ('26 Oct 2026, 17:12', 'OpenStreetMap is the permanent default', 'OpenFreeMap is the automatic backup',
                  'OpenFreeMap © OpenMapTiles Data from OpenStreetMap', 'No Stadia', 'MapTiler is never the default', 'Rule 23'):
            self.assertIn(s, doc)


EN_CREDIT = 'Map © OpenStreetMap contributors. Backup map: OpenFreeMap © OpenMapTiles. © MapTiler.'
CY_CREDIT = 'Map © cyfranwyr OpenStreetMap. Map wrth gefn: OpenFreeMap © OpenMapTiles. © MapTiler.'


def _read(rel):
    return open(os.path.join(R, rel), encoding='utf-8').read()


def _text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html))


class MapCredits(unittest.TestCase):
    """Dean 26 Oct 19:51: every map credit names OpenStreetMap, OpenFreeMap and MapTiler, in the same words.
    The MapTiler credit is text only; MapTiler stays disabled in tiles.js (MapPolicy above)."""

    def _has_all(self, where, text):
        for name in ('OpenStreetMap', 'OpenFreeMap', 'OpenMapTiles', 'MapTiler'):
            self.assertIn(name, text, where)

    def test_every_credit_uses_the_same_wording(self):
        home = _read('index.html')
        footer = _text(re.search(r'<footer>.*?</footer>', home, re.S).group(0))
        self.assertIn(EN_CREDIT, footer)
        ld = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', home, re.S)]
        credits = [d.get('creditText', '') for d in ld if isinstance(d, dict) and d.get('creditText')]
        self.assertTrue(credits, 'index.html JSON-LD has no creditText')
        for c in credits:
            self.assertIn(EN_CREDIT, c)
        self.assertIn(EN_CREDIT, _read('scripts/seo_meta.py'))
        faq = _read('faq.html')
        faq_text = _text(faq)
        self.assertIn(EN_CREDIT, faq_text)
        self.assertIn(CY_CREDIT, faq_text)
        faq_ld = ' '.join(json.dumps(json.loads(m), ensure_ascii=False)
                          for m in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', faq, re.S))
        self.assertIn(EN_CREDIT, faq_ld, 'FAQ JSON-LD answer')
        for rel in ('terms.html', 'privacy.html'):
            self.assertIn(EN_CREDIT, _text(_read(rel)), rel)
        self.assertIn(CY_CREDIT, _read('layers.js'))  # Welsh footer translation
        for where, t in (('footer', footer), ('faq', faq_text), ('faq-ld', faq_ld), ('terms', _text(_read('terms.html'))),
                         ('privacy', _text(_read('privacy.html'))), ('json-ld', ' '.join(credits))):
            self._has_all(where, t)

    def test_no_page_keeps_an_old_map_credit(self):
        for rel in ('index.html', 'faq.html', 'terms.html', 'privacy.html', 'scripts/seo_meta.py', 'layers.js'):
            t = _read(rel)
            self.assertNotIn('Map © MapTiler © OpenStreetMap', t, rel)
            self.assertNotIn('Stadia', t, rel)
            self.assertNotIn('stadiamaps', t, rel)
        self.assertEqual(re.findall(r'Map: © OpenStreetMap contributors\.(?! Backup)', _read('faq.html')), [])

    def test_every_html_page_has_the_same_map_credit(self):
        """Dean 26 Oct 19:51: the same map credit on every page. Dropping OpenStreetMap, OpenFreeMap or MapTiler fails."""
        missing = []
        for dirpath, dirnames, files in os.walk(R):
            dirnames[:] = [d for d in dirnames if d != '.git']
            for name in files:
                if not name.endswith('.html'):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), R)
                text = _text(_read(rel))
                if EN_CREDIT not in text:
                    missing.append(rel)
                    continue
                for provider in ('OpenStreetMap', 'OpenFreeMap', 'OpenMapTiles', 'MapTiler'):
                    if provider not in text:
                        missing.append('%s dropped %s' % (rel, provider))
        self.assertEqual(missing, [])
        self.assertIn(CY_CREDIT, _text(_read('faq.html')))


if __name__ == '__main__':
    unittest.main()
