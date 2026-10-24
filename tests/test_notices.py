import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def test_gcg_notice_override():
    d = json.load(open(os.path.join(ROOT, 'overrides', 'foodbank_notices.json')))
    assert d['gcg']['notice'].startswith('Closed until further notice')
def test_build_and_card_use_notice():
    assert 'foodbank_notices.json' in open(os.path.join(ROOT, 'scripts', 'build.py')).read()
    assert 'i.notice?' in open(os.path.join(ROOT, 'index.html')).read()
def test_phone_label_west_ardsley():
    d = json.load(open(os.path.join(ROOT, 'overrides', 'phone_labels.json')))
    assert d['west-ardsley'] == 'West Ardsley Friday pantry'
    assert json.load(open(os.path.join(ROOT, 'overrides', 'phones.json')))['west-ardsley'] == '07896 911966'
    assert 'phone_labels.json' in open(os.path.join(ROOT, 'scripts', 'build.py')).read()
    assert 'i.phone_label?' in open(os.path.join(ROOT, 'index.html')).read()
