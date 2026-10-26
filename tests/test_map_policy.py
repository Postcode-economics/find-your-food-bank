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


if __name__ == '__main__':
    unittest.main()
