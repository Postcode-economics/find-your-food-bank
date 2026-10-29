"""Times review list hand check (Dean, 29 Oct 2026): 2 of the 9 'not one clear weekly client-hours block' rows confirmed
from the food bank's own page and published as protected hand-reviewed times; the other 7 stay on the review list.
The Gate: the finder read the centre's general opening hours (Mon-Fri 10am-3pm); the food parcel collection times are 2pm-3pm."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
OT = json.load(open(os.path.join(ROOT, 'overrides', 'opening_times.json')))
FIXED = {
    'ifan-84cd0bf40986bfc9a427c6-0': ('Wednesday 10am - 2pm (food bags, no referral needed)', 'https://www.laurenceslarder.org.uk'),
    'the-gate': ('Monday to Friday 2pm - 3pm (food parcel collection or by arrangement with staff; referral needed for a standard parcel)',
                 'https://the-gate-charity.org/contact-us-2/'),
}
STILL_QUEUED = ['bow', 'ifan-3c7cb974c7ac6c1966b83c-0', 'ifan-a2fb0701e0208ee9e642a3-0', 'ifan-9fef48d4f0fd3a3f6896d2-0',
                'ifan-53c68645aa831ab649ac43-0', 'community-essentials', 'moorland']

def items():
    s = open(os.path.join(ROOT, 'data.full.js'), encoding='utf-8').read()
    return {i['id']: i for i in json.loads(s[s.index('{'): s.rindex('}') + 1])['items']}

def test_hand_checked_entries_protected_with_quotes():
    for k, (raw, url) in FIXED.items():
        e = OT[k]
        assert e['protected'] is True and e['reader'].startswith('hand-reviewed 2026-10-29'), k
        assert e['raw'] == raw and e['source_url'] == url and e['status'] == 'TIMES_TEXT_ONLY' and e['structured'] is None, k
        assert e['quote'] and all(q for q in e['quote']), k

def test_cards_show_the_hand_checked_times():
    ix = items()
    for k, (raw, url) in FIXED.items():
        ot = ix[k]['opening_times']
        assert ot['raw'] == raw and ot['lines'] == [raw] and ot['protected'] is True and ot['source_url'] == url, k
        assert ix[k]['times_status'] == 'confirmed_by_hand', k
    assert '10am - 3pm' not in ix['the-gate']['opening_times']['raw']

def test_refresh_and_finder_treat_them_as_hand_checked():
    import discover, times_finder
    ix = items()
    for k in FIXED:
        assert discover.hand_checked(ix[k], 'opening_times'), k
        why = times_finder.strict_checks(k, {'raw': 'Monday 9am - 5pm', 'source_url': FIXED[k][1]}, ix[k], OT, {}, 1, {'pages': {}, 'skip': {}}, {}, {})
        assert 'hand-checked times are protected; finder only flags differences' in why, k

def test_logged_with_old_value_and_undo():
    log = json.load(open(os.path.join(ROOT, 'reports', 'times_auto_applied.json')))
    for k, (raw, url) in FIXED.items():
        rec = [r for r in log if r['id'] == k]
        assert len(rec) == 1, k
        r = rec[0]
        assert r['old'] is None and r['new']['raw'] == raw and r['source_url'] == url, k
        assert r['revert'] == 'python scripts/times_revert.py ' + k and 'path' not in r and not r.get('reverted'), k

def test_review_list_drops_only_the_resolved_rows():
    t = open(os.path.join(ROOT, 'reports', 'pending_dean.md'), encoding='utf-8').read()
    block = t[t.index('<!-- times review -->'): t.index('<!-- /times review -->')]
    for k in FIXED: assert '(`%s`,' % k not in block, k
    for k in STILL_QUEUED: assert '(`%s`,' % k in block, k
