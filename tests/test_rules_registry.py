"""Rule 24. One test per rule from 19 to 26. A rule in this range with no test_rule_<n>_ fails this file.

Rule 27 (opening times) is owned elsewhere and is not asserted here.
"""
import inspect, os, re, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import check_browser as B
import phone_rules
import stamp


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


class Registry(unittest.TestCase):
    def test_rule_19_per_layer_stamps(self):
        src = _read('scripts/stamp.py')
        self.assertIn("{'refresh': 'fb', 'shelters': 'sh', 'warmspaces': 'ws'}", src)
        self.assertIn('stamp.py verify', _read('.github/workflows/refresh.yml'))
        self.assertIn('stamp.py write shelters && python scripts/stamp.py verify', _read('.github/workflows/refresh-shelters.yml'))
        self.assertIn('stamp.py write warmspaces && python scripts/stamp.py verify', _read('.github/workflows/refresh-warmspaces.yml'))
        a = {'run': '2026-01-01T00:00:00+00:00', 'layers': {
            'fb': {'run': '2026-01-02T00:00:00+00:00', 'label': 'fb-new'},
            'sh': {'run': '2026-01-01T00:00:00+00:00', 'label': 'sh-old'}}}
        b = {'run': '2026-01-03T00:00:00+00:00', 'layers': {
            'fb': {'run': '2026-01-01T00:00:00+00:00', 'label': 'fb-old'},
            'ws': {'run': '2026-01-03T00:00:00+00:00', 'label': 'ws'}}}
        out = stamp.combine(a, b)
        self.assertEqual(out['layers']['fb']['label'], 'fb-new')
        self.assertEqual(out['layers']['sh']['label'], 'sh-old')
        self.assertEqual(out['layers']['ws']['label'], 'ws')

    def test_rule_20_links_open_the_latest_version(self):
        sw = _read('sw.js')
        self.assertIn("mode==='navigate'", sw)
        self.assertIn("cache:'no-cache'", sw)
        refresh = _read('.github/workflows/refresh.yml')
        self.assertLess(refresh.index('git commit'), refresh.index('scripts/indexnow.py'))

    def test_rule_21_phone_label_from_the_page_then_the_override(self):
        item = {'phone': '01234 567890', 'tel': '01234567890'}
        self.assertEqual(phone_rules.apply_contact_label(item, 'Manager', 'Pastor 01234 567890'), 'page')
        self.assertEqual(item['phone_label'], 'Pastor')
        build = _read('scripts/build.py')
        self.assertIn('phone_labels.json', build)
        self.assertIn('apply_contact_label', build)
        self.assertIn('phone_label', _read('index.html'))

    def test_rule_22_osm_is_the_default_and_a_backup_is_wired(self):
        tiles = _read('tiles.js')
        self.assertIn("name: 'osm'", tiles)
        self.assertIn('https://tile.openstreetmap.org/{z}/{x}/{y}.png', tiles)
        self.assertIn('n < list.length - 1', tiles)
        self.assertRegex(tiles, r"name: 'maptiler', key: ''")
        self.assertRegex(tiles, r"name: 'stadia', key: ''")

    def test_rule_23_every_check_context_serves_placeholder_tiles(self):
        self.assertIn('install_tile_stub(c)', inspect.getsource(B.new_context))
        self.assertNotIn('continue_', inspect.getsource(B.fulfill_tile))
        self.assertTrue(B.is_tile_host('https://tile.openstreetmap.org/0/0/0.png'))
        self.assertTrue(B.is_tile_host('https://a.tile.openstreetmap.org/1/0/0.png'))
        self.assertFalse(B.is_tile_host('http://127.0.0.1/tile.openstreetmap.org/5/15/9.png'))
        sense = _read('scripts/sense_check.py')
        self.assertIn('new_context', sense)

    def test_rule_24_registry_covers_19_to_26(self):
        names = [n for n, _ in inspect.getmembers(Registry, inspect.isfunction)]
        covered = set()
        for name in names:
            m = re.match(r'test_rule_(\d+)_', name)
            if m:
                covered.add(int(m.group(1)))
        self.assertEqual(covered, set(range(19, 27)))

    def test_rule_25_sense_check_uses_a_local_copy(self):
        sense = _read('scripts/sense_check.py')
        self.assertIn('127.0.0.1', sense)
        self.assertIn('B.new_context', sense)
        self.assertNotIn('https://helpmap.uk', sense)

    def test_rule_26_tiles_are_cache_first(self):
        sw = _read('sw.js')
        start = sw.index('if(TILE.test(u.host))')
        block = sw[start:start + 500]
        self.assertIn('if(hit)return hit', block)
        self.assertLess(block.index('caches.open(T)'), block.index('return fetch(e.request)'))
        self.assertIn(r'tile\.openstreetmap\.org', sw)
        self.assertIn(r'api\.maptiler\.com', sw)
        self.assertIn(r'tiles\.stadiamaps\.com', sw)


if __name__ == '__main__':
    unittest.main()
