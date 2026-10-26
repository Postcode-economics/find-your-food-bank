"""Rule 27 second pass (Dean, 26 Oct 2026): 3 cards re-read live and protected.
Meon Valley: Monday is donations only, so only Tuesday collections are listed.
Soar Valley (card already right) and Ty Hapus (page shows no food bank times) left unchanged."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
OT = json.load(open(os.path.join(ROOT, 'overrides', 'opening_times.json')))
FIXED = {'hedge-end': {'mon', 'thu'}, 'meon-valley': {'tue'}, 'worthing-food-foundation': {'wed', 'fri'}}

def test_fixed_cards_protected_with_quotes():
    for k, days in FIXED.items():
        e = OT[k]
        assert e['protected'] is True and e['reader'].startswith('hand-reviewed'), k
        assert e['status'] == 'TIMES_FOUND' and set(e['structured']) == days, k
        assert e['quote'] and all(e['quote']) and e['source_url'].startswith('https://'), k
        for rs in e['structured'].values():
            for a, b in rs: assert a < b, k

def test_normalise_keeps_hand_fixes():
    from times import normalise
    for k in FIXED: assert normalise(OT[k]) == OT[k]

def test_unconfirmed_left_as_is():
    assert OT['soar-valley-community-food-project']['raw'] == 'Monday morning from 9 -12'
    assert not OT['ty-hapus'].get('protected')
