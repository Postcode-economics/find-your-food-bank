import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def test_gcg_reopened_no_closure_notice():
    d = json.load(open(os.path.join(ROOT, 'overrides', 'foodbank_notices.json')))
    assert 'gcg' not in d
    r = d['_removed']['gcg']
    assert 'GREAT NEWS' in r['why'] and 'WE HAVE NO BAGS' in r['why']
    t = open(os.path.join(ROOT, 'data.full.js'), encoding='utf-8').read()
    items = json.loads(t[t.index('=') + 1:].strip().rstrip(';'))['items']
    gcg = next(i for i in items if i['id'] == 'gcg')
    assert 'notice' not in gcg
def test_build_and_card_use_notice():
    assert 'foodbank_notices.json' in open(os.path.join(ROOT, 'scripts', 'build.py')).read()
    assert 'i.notice?' in open(os.path.join(ROOT, 'index.html')).read()
def test_phone_label_west_ardsley():
    d = json.load(open(os.path.join(ROOT, 'overrides', 'phone_labels.json')))
    assert d['west-ardsley'] == 'West Ardsley Friday pantry'
    assert json.load(open(os.path.join(ROOT, 'overrides', 'phones.json')))['west-ardsley'] == '07896 911966'
    assert 'phone_labels.json' in open(os.path.join(ROOT, 'scripts', 'build.py')).read()
    assert 'i.phone_label?' in open(os.path.join(ROOT, 'index.html')).read()
def test_west_ardsley_venue():
    a = json.load(open(os.path.join(ROOT, 'overrides', 'foodbank_address_fixes.json')))['west-ardsley']
    assert a['postcode'] == 'WF3 1HD' and 'Batley Road' in a['address']
    t = json.load(open(os.path.join(ROOT, 'overrides', 'opening_times.json')))['west-ardsley']
    assert t['structured'] == {'fri': [['11:00', '12:30']]}
    for f in ('foodbank_address_fixes.json', 'phones.json', 'phone_sources.json', 'opening_times.json'):
        s = open(os.path.join(ROOT, 'overrides', f)).read()
        assert 'west-ardsley' not in s or ('2522927' not in s.replace(' ', '') and 'WF3 1EN' not in s)
def test_invergordon_joss_street():
    a = json.load(open(os.path.join(ROOT, 'overrides', 'foodbank_address_fixes.json')))
    assert a['invergordon']['postcode'] == 'IV18 0AP' and '9 Joss Street' in a['invergordon']['address']
    assert 'highland/alness-invergordon' not in a
    assert json.load(open(os.path.join(ROOT, 'overrides', 'phones.json')))['invergordon'] == '07803259452'
