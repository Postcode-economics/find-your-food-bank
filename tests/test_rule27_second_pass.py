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

def test_soar_valley_left_as_is():
    assert OT['soar-valley-community-food-project']['raw'] == 'Monday morning from 9 -12'

def test_ty_hapus_shows_no_times_and_is_unclear():
    # Page times belong to a boxing club and a toddler group (Dean approved removal 26 Oct).
    e = OT['ty-hapus']
    assert e['protected'] is True and e['reader'].startswith('hand-reviewed') and e['unclear'] is True
    assert e['raw'] == '' and e['structured'] is None and e['quote'] and e['previous']
    from times import normalise
    import hours_norm
    n = hours_norm.normalise_fb(normalise(e))
    # The card falls back to the standard no-times line only when there is no raw text and no structured times.
    assert not (n or {}).get('raw') and not (n or {}).get('structured') and not (n or {}).get('lines')
    g = json.load(open(os.path.join(ROOT, 'overrides', 'guard_wrong_times.json')))
    assert 'ty-hapus' in g['foodbanks']
