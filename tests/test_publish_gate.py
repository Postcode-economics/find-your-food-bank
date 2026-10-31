import json, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import publish_gate as pg
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

def test_problems():
    assert pg.problems('shelters', {'tel': '01', 'groups': ['Men']}) == []
    assert pg.problems('shelters', {'council_ooh': '0300', 'groups': []}) == ["no sourced 'who it's for'"]
    assert pg.problems('warmspaces', {}) == ['no verified phone']
    assert pg.problems('foodbanks', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01', 'council_label': 'x'}) == []

def test_council_listed_warmspace_auto_ok_without_approved_list():
    feed = 'https://services1.arcgis.com/KZuCGRSe2K5BiG1Z/arcgis/rest/services/WarmHubs/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&returnGeometry=true&f=json'
    ok_row = dict(id='th-e11bu-test', name='Test Hub', address='1 Road', postcode='E1 1BU', tel='03333704700',
                  source_url=feed, source='Tower Hamlets warm hubs')
    assert pg.council_listed_warmspace(ok_row)
    assert pg.problems('warmspaces', ok_row) == []
    no_phone = dict(ok_row, tel='')
    assert not pg.council_listed_warmspace(no_phone)
    assert pg.problems('warmspaces', no_phone) == ['no verified phone']
    lancs = dict(ok_row, id='lancs-bb11-test', source_url='https://services-eu1.arcgis.com/x')
    assert not pg.council_listed_warmspace(lancs)
    assert pg.LANCS_HOLD in pg.warmspace_publish_holds(lancs)

def test_published_data_passes_check():
    assert pg.check() == 0

ADDR = '99 Dummy Lane, Exampletown EX1 1EX'

def _run_gate(layer, live, now, meta=None, phones_json='{"a": "01"}'):
    """The gate as the refresh workflow runs it: python scripts/publish_gate.py <layer>, on a repo whose HEAD has `live`
    and whose working file has `now`. Returns (exit code, ids left in the file, pending ids)."""
    d = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(ROOT, 'scripts'), os.path.join(d, 'scripts'), ignore=shutil.ignore_patterns('__pycache__'))
        for sub in ('logs', 'reports', 'overrides'): os.makedirs(os.path.join(d, sub))
        shutil.copy(os.path.join(ROOT, 'overrides', 'auto_apply_rules.json'), os.path.join(d, 'overrides'))
        path = os.path.join(d, pg.FILES[layer])
        body = lambda items: 'window.X=' + json.dumps(dict(meta or {}, items=items)) + ';'
        open(path, 'w').write(body(live))
        git = lambda *a: subprocess.run(a, cwd=d, check=True, capture_output=True)
        git('git', 'init', '-q'); git('git', 'add', '-A'); git('git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'base')
        open(path, 'w').write(body(now))
        open(os.path.join(d, 'overrides', 'phones.json'), 'w').write(phones_json)
        r = subprocess.run([sys.executable, os.path.join('scripts', 'publish_gate.py'), layer], cwd=d, capture_output=True, text=True,
                           env=dict(os.environ, PRIVATE_BLOCKLIST=ADDR))
        left = [i['id'] for i in pg.split(open(path).read())[1]['items']]
        pending = [x['id'] for x in json.load(open(os.path.join(d, 'logs', 'pending_dean.json'))).get(layer, [])]
        return r.returncode, left, pending, r.stdout
    finally:
        shutil.rmtree(d, True)

def test_held_hand_file_still_runs_every_check_and_blocks():
    """Review 28 Oct: a broken overrides/phones.json made gate() return before the new-place, phone and blocklist
    checks, and the step exited 0, so an unapproved new shelter with no phone was published."""
    live = dict(id='s-live', name='Live', tel='01000000001', groups=['Men'])
    home = dict(id='s-home', name='Home', address=ADDR, tel='01000000002', groups=['Men'])
    new = dict(id='s-new', name='New Shelter', groups=['Men'])
    code, left, pending, out = _run_gate('shelters', [live, home], [live, home, new], phones_json='{not json')
    assert code == 1, out
    assert left == ['s-live']
    assert set(pending) == {'s-new', 's-home'}
    assert 'publish blocked' in out
    code, left, _, out = _run_gate('shelters', [live], [live])
    assert (code, left) == (0, ['s-live']), out

def test_rejected_schema_still_runs_every_check_and_blocks():
    live = dict(id='fb-live', name='Live', tel='01000000001')
    new = dict(id='fb-new', name='New Food Bank')
    code, left, pending, out = _run_gate('foodbanks', [live], [live, new], meta={'schema_version': 99})
    assert code == 1, out
    assert left == ['fb-live'] and pending == ['fb-new']
    assert "schema_version 99 is not accepted" in out
    code, left, pending, out = _run_gate('foodbanks', [live], [live, new], meta={'schema_version': 1})
    assert code == 0, out
    assert left == ['fb-live'] and pending == ['fb-new']
