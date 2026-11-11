import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from times import normalise
T = lambda raw: normalise({'raw': raw, 'status': 'TIMES_TEXT_ONLY', 'structured': None})
def test_bognor():
    r = T('Tuesdays 10.30am – 2.30pm | Thursdays 11am – 1pm | Fridays 10.30am – 2.30pm | Mon Closed Tue 10:30 - 14:30 | Wed Closed Thu 11:00 - 13:00 | Fri 10:30 - 14:30')
    assert r['status'] == 'TIMES_FOUND' and r['structured'] == {'tue': [['10:30', '14:30']], 'thu': [['11:00', '13:00']], 'fri': [['10:30', '14:30']]}
def test_prose():
    assert T('Mon – Thurs 10.30 am – 3:00pm')['structured']['thu'] == [['10:30', '15:00']]
    assert T('Monday, Wednesday and Friday 12.00 – 2.00')['structured']['wed'] == [['12:00', '14:00']]
def test_monthly_falls_back():
    r = T('Wednesday of the month 10:00am to 12:00pm | Wednesday of the month 10:00am to 12:00pm')
    assert r['status'] == 'TIMES_TEXT_ONLY' and r['lines'] == ['Wednesday of the month 10:00am to 12:00pm']
def test_conflict_falls_back():
    assert T('Mon 10:00 - 12:00 | Mon 13:00 - 15:00')['status'] == 'TIMES_TEXT_ONLY'
def test_weekdays_means_monday_to_friday():
    r = T('weekdays 10.30am – 1pm')
    assert r['status'] == 'TIMES_FOUND'
    assert r['structured'] == {d: [['10:30', '13:00']] for d in ('mon', 'tue', 'wed', 'thu', 'fri')}
def test_referral_weekdays_are_not_a_table():
    r = T('Open for referrals: weekdays 10am – 12.30pm')
    assert r is None or r.get('status') != 'TIMES_FOUND' or not r.get('structured')
def test_weekly_is_still_not_a_table():
    r = T('every week Tuesday 10am – 12pm')
    assert r is None or r.get('status') != 'TIMES_FOUND' or not r.get('structured')
def test_placeholder():
    assert T('Opening times Mon Closed Tue Closed Wed Closed Thu Closed Fri Closed Sat Closed Sun Closed') is None
if __name__ == '__main__':
    for k, v in list(globals().items()):
        if k.startswith('test_'): v(); print('ok', k)
