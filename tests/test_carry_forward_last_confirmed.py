"""A malformed confirmation date (e.g. '27/10/2026') never reaches the 'Not re-confirmed since' card note: the label
falls back to the next valid date, then to carried_since."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import carry_forward as C

V = {'id': 'ww-v', 'name': 'Village Hall', 'postcode': 'E9 9AB', 'lat': 51.0, 'lng': 0.5, 'hours': {'Wed': '10:00 - 12:00'}, 'stale': False}
NOTE = 'Not re-confirmed since %s – call before you go'


class LastConfirmed(unittest.TestCase):
    def carried(self, o): return C.carry_items([o], [], [], '2026-10-28', allowed=set())[1][0]

    def test_malformed_last_confirmed_falls_back_to_carried_since(self):
        c = self.carried(dict(V, last_confirmed='27/10/2026'))
        self.assertEqual(c['carried_note'], NOTE % '2026-10-28'); self.assertNotIn('last_confirmed', c)

    def test_malformed_last_verified_falls_back_to_carried_since(self):
        self.assertEqual(self.carried(dict(V, last_verified='27/10/2026'))['carried_note'], NOTE % '2026-10-28')

    def test_malformed_value_falls_back_to_the_next_valid_date(self):
        c = self.carried(dict(V, last_confirmed='2026-13-45', last_verified='2026-10-20'))
        self.assertEqual((c['carried_note'], c['last_confirmed']), (NOTE % '2026-10-20', '2026-10-20'))
        self.assertEqual(C.last_confirmed(dict(V, last_confirmed='not a date', verified_on='2026-10-19T08:00:00Z')), '2026-10-19')

    def test_valid_dates_are_unchanged(self):
        self.assertEqual(self.carried(dict(V, last_confirmed='2026-10-21'))['carried_note'], NOTE % '2026-10-21')
        self.assertEqual(C.last_confirmed(V, {'ww-v': '2026-10-22T09:00:00+00:00'}), '2026-10-22')
        self.assertEqual(C.last_confirmed(V), '')


if __name__ == '__main__': unittest.main()
