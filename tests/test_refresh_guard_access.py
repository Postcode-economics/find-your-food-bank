"""29 Oct 08:48 refresh (b55354853): the guard kept places in data.full.js that the run dropped, but build.py had already
rebuilt access.js from the places it built, so 12 published food banks lost their filter-chip tag. The guard now
carries the tag over, and the refresh fails if any published food bank loses a tag it had."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import refresh_guard as G

PLACE = lambda i: {'id': i, 'name': i.title(), 'lat': 51.0, 'lng': -1.0, 'phone': '01000 000000', 'opening_times': None}

def write(root, items, acc):
    open(os.path.join(root, 'data.full.js'), 'w').write('window.FB_DATA=' + json.dumps({'items': items}) + ';')
    G.write_access(acc, root)

def read_acc(root):
    s = open(os.path.join(root, 'access.js')).read(); return json.loads(s[s.index('{'):s.rindex('}') + 1])

class GuardKeepsAccessTag(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d)
        for sub in ('logs', 'reports'): os.makedirs(os.path.join(self.d, sub))
        git = lambda *a: subprocess.run(['git', *a], cwd=self.d, check=True, capture_output=True)
        git('init', '-q'); git('config', 'user.email', 't@t'); git('config', 'user.name', 't')
        write(self.d, [PLACE('kept'), PLACE('stays'), dict(PLACE('depot'), kind='warehouse')], {'kept': 'walkin', 'stays': 'voucher'})
        git('add', '-A'); git('commit', '-qm', 'published')
        for p in (mock.patch.object(G, 'ROOT', self.d), mock.patch.dict(os.environ, {'GH_TOKEN': ''})):
            p.start(); self.addCleanup(p.stop)

    def test_guard_kept_place_keeps_its_access_tag(self):
        write(self.d, [PLACE('stays'), dict(PLACE('depot'), kind='warehouse')], {'stays': 'walkin'})    # this run dropped 'kept'; a full-check flip on 'stays'
        rep = G.main('foodbanks')
        self.assertEqual(rep['places'], ['kept']); self.assertEqual(rep['access'], ['kept'])
        self.assertEqual(read_acc(self.d), {'stays': 'walkin', 'kept': 'walkin'})   # this run's tags win; the kept one is back

    def test_refresh_fails_if_a_published_place_loses_its_tag(self):
        write(self.d, [PLACE('kept'), PLACE('stays'), dict(PLACE('depot'), kind='warehouse')], {'kept': 'walkin'})
        with self.assertRaises(SystemExit) as e: G.main('foodbanks')
        self.assertEqual(e.exception.code, 1)
        self.assertEqual(read_acc(self.d), {'kept': 'walkin'})   # nothing written

    def test_untagged_kinds_and_new_places_are_not_losses(self):
        old = {'a': 'voucher', 'depot': 'walkin'}
        self.assertEqual(G.lost_access([PLACE('a'), dict(PLACE('depot'), kind='warehouse'), PLACE('new')], old, {'a': 'voucher'}), [])
        self.assertEqual(G.lost_access([PLACE('a')], old, {}), ['a'])

class PublishedAccessComplete(unittest.TestCase):
    def test_every_published_food_bank_that_had_a_tag_still_has_one(self):
        root = os.path.join(os.path.dirname(__file__), '..')
        ld = lambda p: (lambda s: json.loads(s[s.index('{'):s.rindex('}') + 1]))(open(os.path.join(root, p), encoding='utf-8').read())
        items, acc = ld('data.full.js')['items'], ld('access.js')
        self.assertEqual([i['id'] for i in items if i['id'] not in acc and i.get('kind') not in G.NO_TAG], [])

if __name__ == '__main__': unittest.main()
