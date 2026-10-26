import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import publish_gate as pg

def test_approved_foodbank_without_a_phone_is_not_held():
    ok = {'ifan-b595a2208802ba38bef45d-0'}
    assert pg.hold_reasons('foodbanks', {'id': 'ifan-b595a2208802ba38bef45d-0'}, False, ok, False) == []
    held = pg.hold_reasons('foodbanks', {'id': 'brand-new'}, False, ok, False)
    assert held[0].startswith('new place') and 'no verified phone' in held
    assert pg.hold_reasons('shelters', {'id': 'x', 'groups': ['Men']}, False, {'x'}, False) == ['no verified phone']
    assert pg.hold_reasons('foodbanks', {'id': 'old', 'phone': ''}, True, set(), False) == []

def test_problems():
    assert pg.problems('shelters', {'tel': '01', 'groups': ['Men']}) == []
    assert pg.problems('shelters', {'council_ooh': '0300', 'groups': []}) == ["no sourced 'who it's for'"]
    assert pg.problems('warmspaces', {}) == ['no verified phone']
    assert pg.problems('foodbanks', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01', 'council_label': 'x'}) == []

def test_published_data_passes_check():
    assert pg.check() == 0
