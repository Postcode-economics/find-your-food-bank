import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import refresh_guard as g

def test_keeps_dropped_place_phone_and_hours():
    old = [{'id': 'a', 'name': 'A', 'lat': 1, 'lng': 1, 'tel': '0111', 'phone': '0111', 'hours': 'Mon 9-5'},
           {'id': 'b', 'name': 'B', 'lat': 2, 'lng': 2, 'tel': '0222', 'phone': '0222', 'hours': 'Tue'}]
    new = [{'id': 'a', 'name': 'A', 'lat': 1, 'lng': 1, 'tel': '', 'phone': '', 'hours': ''}]
    out, rep = g.guard('shelters', old, new)
    assert rep == {'places': ['b'], 'phones': ['a'], 'times': ['a']}
    assert {i['id'] for i in out} == {'a', 'b'} and out[0]['tel'] == '0111' and out[0]['hours'] == 'Mon 9-5'

def test_rekeyed_place_and_deliberate_phone_drop_not_restored():
    old = [{'id': 'x1', 'name': 'Hub', 'lat': 1, 'lng': 1, 'tel': '0333', 'phone': '0333', 'hours': 'h'}]
    new = [{'id': 'x2', 'name': 'Hub', 'lat': 1.0001, 'lng': 1, 'tel': '', 'phone': '', 'phone_was': '0333', 'hours': 'h'}]
    out, rep = g.guard('warmspaces', old, new)
    assert rep == {'places': [], 'phones': [], 'times': []} and len(out) == 1

def test_food_bank_times():
    old = [{'id': 'f', 'name': 'F', 'lat': 1, 'lng': 1, 'phone': '1', 'opening_times': {'raw': 'Mon 10-12', 'checked_date': '2026-10-20'}}]
    new = [{'id': 'f', 'name': 'F', 'lat': 1, 'lng': 1, 'phone': '1', 'opening_times': {'status': 'NOT_FOUND'}}]
    out, rep = g.guard('foodbanks', old, new)
    assert rep['times'] == ['f'] and out[0]['opening_times']['raw'] == 'Mon 10-12'
