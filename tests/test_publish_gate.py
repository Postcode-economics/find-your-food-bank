import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import publish_gate as pg

def test_problems():
    assert pg.problems('shelters', {'tel': '01', 'groups': ['Men']}) == []
    # An unlabelled council number is not a verified phone (rule 5).
    assert pg.problems('shelters', {'council_ooh': '0300', 'groups': []}) == ['no verified phone', "no sourced 'who it's for'"]
    assert pg.problems('shelters', {
        'council_ooh': '03001234567', 'council_phone': '03001234567',
        'council_label': 'Council out-of-hours homeless line',
        'council_url': 'https://www.example.gov.uk/homelessness', 'groups': ['Men']}) == []
    assert pg.problems('warmspaces', {}) == ['no verified phone']
    assert pg.problems('foodbanks', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01'}) == ['no verified phone']
    assert pg.problems('warmspaces', {'council_phone': '01', 'council_label': 'x'}) == ['no verified phone']
    assert pg.problems('warmspaces', {
        'council_phone': '01354654321', 'council_label': 'Council switchboard',
        'council_url': 'https://www.example.gov.uk/contact'}) == ['no verified phone']
    assert pg.problems('warmspaces', {
        'council_phone': '01354654321', 'council_label': 'Council out-of-hours homeless line',
        'council_url': 'https://www.example.gov.uk/homelessness'}) == []

def test_published_data_passes_check():
    assert pg.check() == 0
