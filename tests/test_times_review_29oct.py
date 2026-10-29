"""Times review list hand check (Dean, 29 Oct 2026): hand-checked times from own pages published as protected overrides.
Bow: walk-in Visit Us and Wednesday open session structured; Click and Collect in text with order deadlines.
Neo Community: Food and Supplies Market only; Community Café and club sessions left out.
Gospel Church: Food Bank Friday 5pm-6pm only from Church weekly schedule.
St Paul's Pantry: fortnightly foodbank Thu 6:30-7:30 only; church open times left out."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
OT = json.load(open(os.path.join(ROOT, 'overrides', 'opening_times.json')))
FIXED_TEXT = {
    'ifan-84cd0bf40986bfc9a427c6-0': ('Wednesday 10am - 2pm (food bags, no referral needed)', 'https://www.laurenceslarder.org.uk'),
    'the-gate': ('Monday to Friday 2pm - 3pm (food parcel collection or by arrangement with staff; referral needed for a standard parcel)',
                 'https://the-gate-charity.org/contact-us-2/'),
}
FIXED_TABLE = {
    'bow': (
        'Tuesdays 10am - 12pm and Thursdays 10am - 1pm (visit us); Wednesdays 2pm - 7pm (open to all). '
        'Click and Collect: Tuesdays 1pm - 4:30pm (order by 1pm Sunday); Fridays 8am - 12pm (order by 9pm Wednesday)',
        'https://www.bowfoodbank.org',
        {'tue': [['10:00', '12:00']], 'wed': [['14:00', '19:00']], 'thu': [['10:00', '13:00']]}),
    'ifan-3c7cb974c7ac6c1966b83c-0': (
        'Food and Supplies Market: Monday 12pm - 2pm; Tuesday 12pm - 2pm; Wednesday 12pm - 2pm; '
        'Friday 12pm - 2pm; Saturday 11am - 1pm (Thursday closed)',
        'https://www.neocommunity.org.uk/',
        {'mon': [['12:00', '14:00']], 'tue': [['12:00', '14:00']], 'wed': [['12:00', '14:00']],
         'fri': [['12:00', '14:00']], 'sat': [['11:00', '13:00']]}),
    'ifan-9fef48d4f0fd3a3f6896d2-0': (
        'Food Bank: Fridays 5pm - 6pm',
        'https://www.gcjc.co.uk',
        {'fri': [['17:00', '18:00']]}),
    'ifan-53c68645aa831ab649ac43-0': (
        'Every other Thursday, 6:30pm to 7:30pm, in church',
        'https://stpaulsparkside.org.uk/',
        {'thu': [['18:30', '19:30']]}),
}
STILL_QUEUED = ['community-essentials', 'moorland']

def items():
    s = open(os.path.join(ROOT, 'data.full.js'), encoding='utf-8').read()
    return {i['id']: i for i in json.loads(s[s.index('{'): s.rindex('}') + 1])['items']}

def test_hand_checked_entries_protected_with_quotes():
    for k, (raw, url) in FIXED_TEXT.items():
        e = OT[k]
        assert e['protected'] is True and e['reader'].startswith('hand-reviewed 2026-10-29'), k
        assert e['raw'] == raw and e['source_url'] == url and e['status'] == 'TIMES_TEXT_ONLY' and e['structured'] is None, k
        assert e['quote'] and all(q for q in e['quote']), k
    for k, (raw, url, structured) in FIXED_TABLE.items():
        e = OT[k]
        assert e['protected'] is True and e['reader'].startswith('hand-reviewed 2026-10-29'), k
        assert e['raw'] == raw and e['source_url'] == url and e['status'] == 'TIMES_FOUND' and e['structured'] == structured, k
        assert e['quote'] and all(q for q in e['quote']), k
    assert 'Community Café' not in OT['ifan-3c7cb974c7ac6c1966b83c-0']['raw']
    assert 'thu' not in OT['ifan-3c7cb974c7ac6c1966b83c-0']['structured']
    gc = OT['ifan-9fef48d4f0fd3a3f6896d2-0']
    assert 'Bible Study' not in gc['raw'] and 'Street Evangelism' not in gc['raw']
    assert list(gc['structured'].keys()) == ['fri']
    sp = OT['ifan-53c68645aa831ab649ac43-0']
    assert 'Every other Thursday' in sp['raw'] and sp['notes']['thu'] == 'Fortnightly'
    assert list(sp['structured'].keys()) == ['thu']
    assert 'Monday' not in sp['raw'] and 'Tuesday' not in sp['raw'] and 'Wednesday' not in sp['raw']

def test_cards_show_the_hand_checked_times():
    ix = items()
    for k, (raw, url) in FIXED_TEXT.items():
        ot = ix[k]['opening_times']
        assert ot['raw'] == raw and ot['lines'] == [raw] and ot['protected'] is True and ot['source_url'] == url, k
        if k == 'the-gate':
            assert ix[k]['times_status'] == 'confirmed_by_hand', k
    assert '10am - 3pm' not in ix['the-gate']['opening_times']['raw']
    for k, (raw, url, structured) in FIXED_TABLE.items():
        ot = ix[k]['opening_times']
        assert ot['raw'] == raw and ot['structured'] == structured and ot['protected'] is True and ot['source_url'] == url, k
        assert ot['status'] == 'TIMES_FOUND' and ix[k]['times_status'] == 'confirmed_by_hand', k
    neo = ix['ifan-3c7cb974c7ac6c1966b83c-0']['opening_times']
    assert '4:30pm' not in neo['raw'] and 'Communi-tea' not in neo['raw']
    gc = ix['ifan-9fef48d4f0fd3a3f6896d2-0']['opening_times']
    assert gc['structured']['fri'] == [['17:00', '18:00']]
    assert 'Sunday' not in gc['raw']
    sp = ix['ifan-53c68645aa831ab649ac43-0']['opening_times']
    assert sp['notes']['thu'] == 'Fortnightly' and sp['structured']['thu'] == [['18:30', '19:30']]
    assert 'Every other Thursday' in sp['raw']

def test_refresh_and_finder_treat_them_as_hand_checked():
    import discover, times_finder
    ix = items()
    for k in FIXED_TEXT:
        assert discover.hand_checked(ix[k], 'opening_times'), k
        why = times_finder.strict_checks(k, {'raw': 'Monday 9am - 5pm', 'source_url': FIXED_TEXT[k][1]}, ix[k], OT, {}, 1, {'pages': {}, 'skip': {}}, {}, {})
        assert 'hand-checked times are protected; finder only flags differences' in why, k
    for k, (raw, url, _) in FIXED_TABLE.items():
        assert discover.hand_checked(ix[k], 'opening_times'), k
        why = times_finder.strict_checks(k, {'raw': 'Monday 9am - 5pm', 'source_url': url}, ix[k], OT, {}, 1, {'pages': {}, 'skip': {}}, {}, {})
        assert 'hand-checked times are protected; finder only flags differences' in why, k

def test_logged_with_old_value_and_undo():
    log = json.load(open(os.path.join(ROOT, 'reports', 'times_auto_applied.json')))
    for k, (raw, url) in FIXED_TEXT.items():
        rec = [r for r in log if r['id'] == k]
        assert len(rec) == 1, k
        r = rec[0]
        assert r['old'] is None and r['new']['raw'] == raw and r['source_url'] == url, k
        assert r['revert'] == 'python scripts/times_revert.py ' + k and 'path' not in r and not r.get('reverted'), k
    for k, (raw, url, structured) in FIXED_TABLE.items():
        rec = [r for r in log if r['id'] == k]
        assert len(rec) == 1, k
        r = rec[0]
        assert r['old'] is None and r['new']['raw'] == raw and r['source_url'] == url
        assert r['new']['structured'] == structured and r['revert'] == 'python scripts/times_revert.py ' + k

def test_review_list_drops_only_the_resolved_rows():
    t = open(os.path.join(ROOT, 'reports', 'pending_dean.md'), encoding='utf-8').read()
    block = t[t.index('<!-- times review -->'): t.index('<!-- /times review -->')]
    for k in list(FIXED_TEXT) + list(FIXED_TABLE):
        assert '(`%s`,' % k not in block, k
    for k in STILL_QUEUED:
        assert '(`%s`,' % k in block, k
