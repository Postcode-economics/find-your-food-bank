"""Rule 27 card fixes (Dean, 26 Oct 2026 14:21): 29 cards re-read live and protected, Prestwood dropped.
Guards that each hand fix keeps its evidence and stays protected from the 3x-daily refresh."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
OT = json.load(open(os.path.join(ROOT, 'overrides', 'opening_times.json')))
FIXED = {
    'andover/unity': {'mon', 'tue', 'wed', 'thu', 'fri'}, 'bangor-ni': {'mon', 'wed', 'fri'}, 'bangor-ni/hom-portaferry': {'thu'},
    'bradford-north/church-on-the-way': {'mon'}, 'bradford-north/guiseley': {'fri'}, 'bradford-north/shipley': {'mon', 'thu'},
    'bradford-north/trinity-rawdon': {'mon'}, 'bradford-north/windhill': {'tue'}, 'cardiff/cathays': {'tue', 'sat'},
    'cardiff/grangetown': {'fri'}, 'cardiff/llanedeyrn': {'wed', 'fri'}, 'cardiff/splott': {'wed', 'thu'}, 'cardiff/st-mellons': {'mon'},
    'dunbar-foodshare': {'wed'}, 'eastern-valley/victory-church': {'thu'}, 'farnborough/christ-church-cove': {'wed'},
    'kings-darlington': {'mon', 'thu'}, 'kington': {'fri'}, 'lambeth-croydon': {'mon'}, 'lambeth-croydon/dulwich': {'thu'},
    'manchester-south-central/ascension-church-hulme': {'fri'}, 'manchester-south-central/st-brides-church': {'wed'},
    'medway/all-saints-foodbank-centre': {'mon', 'fri'}, 'medway/harvest-foodbank-centre': {'thu'}, 'medway/midkent-college': {'wed'},
    'medway/open-doors-cafe': {'wed'}, 'medway/st-marks-foodbank': {'thu', 'sat'}, 'medway/strood-foodbank': {'tue', 'fri'},
    'west-berks/thatcham': {'thu'},
}

def test_fixed_cards_protected_with_quotes():
    for k, days in FIXED.items():
        e = OT[k]
        assert e['protected'] is True and e['reader'].startswith('hand-reviewed'), k
        assert e['status'] == 'TIMES_FOUND' and set(e['structured']) == days, k
        assert e['quote'] and all(q for q in e['quote']) and e['source_url'].startswith('https://'), k
        for rs in e['structured'].values():
            for a, b in rs: assert a < b, k

def test_normalise_keeps_hand_fixes():
    from times import normalise
    for k in FIXED: assert normalise(OT[k]) == OT[k]

def test_prestwood_delivery_only_not_restored():
    assert 'chiltern/prestwood' not in OT
    g = json.load(open(os.path.join(ROOT, 'overrides', 'guard_wrong_times.json')))
    assert 'chiltern/prestwood' in g['foodbanks']
    import refresh_guard
    old = [{'id': 'chiltern/prestwood', 'name': 'Prestwood', 'lat': 51.7, 'lng': -0.7, 'opening_times': {'raw': 'Tuesday to Friday, 10am to 12:30pm'}}]
    new = [{'id': 'chiltern/prestwood', 'name': 'Prestwood', 'lat': 51.7, 'lng': -0.7}]
    out, rep = refresh_guard.guard('foodbanks', old, new)
    assert 'opening_times' not in out[0] and not rep['times']

def test_discover_keeps_hand_reviewed_times():
    import discover, inspect
    assert 'startswith("hand-reviewed")' in inspect.getsource(discover)
