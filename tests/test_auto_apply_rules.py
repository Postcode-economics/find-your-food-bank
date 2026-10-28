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
    def test_approved_foodbank_without_phone_is_kept(self):
        """Dean 26 Oct: an approved food bank with no published phone (verified details only) stays on the map."""
        d = tempfile.mkdtemp(); run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
        for sub in ('logs', 'reports', 'overrides'): os.makedirs(os.path.join(d, sub))
        w = lambda items: open(os.path.join(d, 'data.full.js'), 'w').write('window.FB_DATA=' + json.dumps({'items': items}) + ';')
        w([dict(id='old', tel='01', name='Old')]); run('git', 'init', '-q'); run('git', 'add', '-A')
        run('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        json.dump({'ok1': {'name': 'Pantry'}}, open(os.path.join(d, 'overrides', 'foodbank_approved_new.json'), 'w'))
        w([dict(id='old', tel='01', name='Old'), dict(id='ok1', name='Pantry'), dict(id='bare', name='Bare')])
        old = G.ROOT; G.ROOT = d
        try: held = G.gate('foodbanks')
        finally: G.ROOT = old
        self.assertEqual([i['id'] for i, _ in held], ['bare'])
        ids = [i['id'] for i in G.split(open(os.path.join(d, 'data.full.js')).read())[1]['items']]
        self.assertEqual(ids, ['old', 'ok1'])
        shutil.rmtree(d)

if __name__ == '__main__': unittest.main()

SCRIPTS = ['build.py', 'closure.py', 'full_check.py', 'publish_gate.py', 'refresh_guard.py', 'build_shelters.py', 'build_warmspaces.py', 'sweep_daily.py', 'swep.py', 'times_finder.py']
class AllScripts(unittest.TestCase):
    def test_every_refresh_script_reads_rules(self):
        for s in SCRIPTS: self.assertIn('auto_rules.load()', open(os.path.join(HERE, '..', 'scripts', s)).read(), s)
    def test_no_layer_auto_adds(self):
        r = auto_rules.load()
        for L in ('foodbanks', 'shelters', 'warmspaces'): self.assertFalse(r['add_new_places'][L], L)
    def test_every_workflow_gates_and_guards_after_build(self):
        """Any workflow that rebuilds a layer file must run publish_gate <layer> then refresh_guard <layer> after the build."""
        wf = os.path.join(HERE, '..', '.github', 'workflows')
        for f, layer, build in (('refresh.yml', 'foodbanks', 'build.py'), ('refresh-shelters.yml', 'shelters', 'build_shelters.py'), ('refresh-warmspaces.yml', 'warmspaces', 'build_warmspaces.py')):
            t = open(os.path.join(wf, f)).read()
            b, g, r = t.index('scripts/' + build), t.index('publish_gate.py ' + layer), t.index('refresh_guard.py ' + layer)
            self.assertTrue(b < g < r, f)
        for f in os.listdir(wf):  # no other workflow may rebuild a layer file without the same gate
            t = open(os.path.join(wf, f)).read()
            for layer, build in (('foodbanks', 'scripts/build.py'), ('shelters', 'scripts/build_shelters.py'), ('warmspaces', 'scripts/build_warmspaces.py')):
                if build in t: self.assertIn('publish_gate.py ' + layer, t, f)

class ClosureModule(unittest.TestCase):
    def test_auto_detected_closure_kept_with_note(self):
        import closure
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'overrides')); os.makedirs(os.path.join(d, 'logs'))
        items = [dict(id='x', name='X', postcode='AB1 2CD', website='https://x.example')]
        orig = closure.check_all; closure.check_all = lambda items, f, t: {'x': {'url': 'https://x.example', 'evidence': 'has now closed'}}
        try: gone = closure.apply(items, d)
        finally: closure.check_all = orig
        self.assertEqual(gone, []); self.assertEqual(len(items), 1); self.assertIn('May have closed', items[0]['notice'])
        shutil.rmtree(d)

class GateAllLayers(unittest.TestCase):
    def test_new_shelter_with_phone_held(self):
        d = tempfile.mkdtemp(); run = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
        for sub in ('logs', 'reports', 'overrides'): os.makedirs(os.path.join(d, sub))
        w = lambda items: open(os.path.join(d, 'shelters.js'), 'w').write('window.SH=' + json.dumps({'items': items}) + ';')
        w([dict(id='a', tel='01', groups=['men'], name='A')]); run('git', 'init', '-q'); run('git', 'add', '-A')
        run('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'b')
        json.dump({'shelters': {'ok': 'Dean'}}, open(os.path.join(d, 'overrides', 'approved_new_places.json'), 'w'))
        w([dict(id='a', tel='01', groups=['men'], name='A'), dict(id='b', tel='02', groups=['men'], name='B'), dict(id='ok', tel='03', groups=['men'], name='OK')])
        old = G.ROOT; G.ROOT = d
        try: held = G.gate('shelters')
        finally: G.ROOT = old
        self.assertEqual([i['id'] for i, _ in held], ['b']); shutil.rmtree(d)

class ApprovedRemovals(unittest.TestCase):
    def test_dean_approved_removal_stays_off(self):
        """Welshpool (Dean 25 Oct 08:57): ids in overrides/foodbank_closed.json are dropped by full_check and never on the pending list."""
        src = open(os.path.join(HERE, '..', 'scripts', 'full_check.py')).read()
        self.assertIn("remove |= {i['id'] for i in items if i['id'] in approved_off}", src)
        self.assertIn("if k not in approved_off", src)
        self.assertIn('welshpool-and-district', json.load(open(os.path.join(HERE, '..', 'overrides', 'foodbank_closed.json'))))
