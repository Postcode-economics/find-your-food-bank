"""Dean 25 Oct 2026 auto-apply rules: no map place added or removed without his OK; config must exist."""
import sys, os, json, unittest, tempfile, subprocess, shutil
HERE = os.path.dirname(__file__); sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import auto_rules, full_check as F, publish_gate as G

class Config(unittest.TestCase):
    def test_config_present_and_strict(self):
        r = auto_rules.load()
        self.assertFalse(r['add_new_places']['foodbanks']); self.assertFalse(r['remove_confirmed_closures'])
        self.assertEqual(r['confirm_runs'], 2); self.assertIn('May have closed', r['closure_card_note'])
        self.assertIn('Dean 25 Oct 2026', r['_comment'])
    def test_missing_config_fails(self):
        old = auto_rules.P; auto_rules.P = '/nonexistent/auto_apply_rules.json'
        try: self.assertRaises(Exception, auto_rules.load)
        finally: auto_rules.P = old
    def test_scripts_read_config(self):
        for s in ('full_check.py', 'publish_gate.py'):
            self.assertIn('auto_rules.load()', open(os.path.join(HERE, '..', 'scripts', s)).read(), s)

class Closure(unittest.TestCase):
    def test_confirmed_closure_kept_with_note(self):
        items = [dict(id='a', type='foodbank', name='A', foodbank='A', website='https://a.example', postcode='X1')]
        store = {'full_check_state.json': {'sites': {'https://a.example': {'perm_closed': 'permanently closed', 'checked_at': 'x'}}, 'ids': ['a']}}
        written = {}; rep = tempfile.mkdtemp()
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site)
        F.rj = lambda n, d: store.get(n, d); F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ('x=', {'items': items}); F.load_access = lambda: {}
        F.write_md = lambda *a: None; F.REP = rep
        F.check_site = lambda u: dict(url=u, ok=True, final_url=u, access='unclear', hours_hash=None, hours_sample=None, seasonal=None, closed='closed', perm_closed='permanently closed', phones=[], tel=None, needs=None, checked_at='y', http=200)
        os.environ['DRY_RUN'] = '1'
        try: F.main()
        finally: F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site = orig; os.environ.pop('DRY_RUN')
        self.assertEqual([i['id'] for i in items], ['a'])          # not removed
        self.assertEqual(items[0]['notice'], F.MAY_CLOSED)          # card note
        self.assertIn('a', written['closures_pending.json'])         # on Dean's list
        self.assertIn('Possible closures', open(os.path.join(rep, 'pending_dean.md')).read())

class NewPlace(unittest.TestCase):
    def test_new_foodbank_held_even_with_phone(self):
        d = tempfile.mkdtemp(); run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
        for sub in ('logs', 'reports', 'overrides'): os.makedirs(os.path.join(d, sub))
        w = lambda items: open(os.path.join(d, 'data.full.js'), 'w').write('window.FB_DATA=' + json.dumps({'items': items}) + ';')
        w([dict(id='old', tel='01', name='Old')]); run('git', 'init', '-q'); run('git', 'add', '-A')
        run('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        json.dump({'ok1': {}}, open(os.path.join(d, 'overrides', 'foodbank_approved_new.json'), 'w'))
        w([dict(id='old', tel='01', name='Old'), dict(id='new', tel='02', name='New'), dict(id='ok1', tel='03', name='OK')])
        old = G.ROOT; G.ROOT = d
        try: held = G.gate('foodbanks')
        finally: G.ROOT = old
        self.assertEqual([i['id'] for i, _ in held], ['new'])
        ids = [i['id'] for i in G.split(open(os.path.join(d, 'data.full.js')).read())[1]['items']]
        self.assertEqual(ids, ['old', 'ok1'])
        self.assertIn('waiting for your OK', open(os.path.join(d, 'reports', 'pending_dean.md')).read())
        shutil.rmtree(d)

if __name__ == '__main__': unittest.main()
