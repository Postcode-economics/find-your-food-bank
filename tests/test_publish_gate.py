import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import publish_gate as pg

def test_problems():
    assert pg.problems('shelters', {'tel': '01', 'groups': ['Men']}) == []
    assert pg.problems('shelters', {'council_ooh': '0300', 'groups': []}) == ["no sourced 'who it's for'"]
    assert pg.problems('warmspaces', {}) == ['no verified phone']
    assert pg.problems('foodbanks', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01', 'council_label': 'x'}) == []

def test_published_data_passes_check():
    assert pg.check() == 0
