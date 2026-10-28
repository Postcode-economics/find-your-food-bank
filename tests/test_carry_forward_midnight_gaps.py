"""Gaps: carry_forward season / scheme boundaries and run identity; refresh_guard across midnight as main() calls it
(no run_day passed), re-run attempts, and logs without a run id."""
import datetime, json, os, shutil, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import carry_forward as C
import refresh_guard as G

V = {'id': 'ww-v', 'name': 'Village Hall', 'postcode': 'E9 9AB', 'lat': 51.0, 'lng': 0.5, 'hours': {'Wed': '10:00 - 12:00'},
     'verified_on': '2026-10-20', 'last_verified': '2026-10-20', 'stale': False}


class Boundaries(unittest.TestCase):
    def carried(self, o, day): return [x['id'] for x in C.carry_items([o], [], [], day, allowed=set(), valid_until=C.season_end)[0]]

    def test_last_day_of_season_is_carried_first_day_after_is_not(self):
        self.assertEqual(self.carried(V, '2027-04-30'), ['ww-v'])
        self.assertEqual(self.carried(V, '2027-05-01'), [])

    def test_season_turns_over_on_1_september(self):
        self.assertEqual(C.season_end({'verified_on': '2026-08-31'}), '2026-04-30')
        self.assertEqual(C.season_end({'verified_on': '2026-09-01'}), '2027-04-30')
        self.assertEqual(self.carried(dict(V, verified_on='2026-08-31', last_verified='2026-08-31'), '2026-10-28'), [])

    def test_scheme_end_day_itself_is_still_carried(self):
        self.assertEqual(self.carried(dict(V, scheme_end='2026-10-28'), '2026-10-28'), ['ww-v'])
        self.assertEqual(self.carried(dict(V, scheme_end='2026-10-28'), '2026-10-29'), [])

    def test_unparseable_confirmation_date_falls_back_to_carried_since(self):
        o = {k: v for k, v in V.items() if k not in ('verified_on', 'last_verified')}
        _, c, _ = C.carry_items([dict(o, last_confirmed='27/10/2026')], [], [], '2026-10-28', allowed=set())
        self.assertEqual(c[0]['carried_note'], 'Not re-confirmed since 2026-10-28 – call before you go')
        _, c, _ = C.carry_items([dict(o, last_verified='27/10/2026')], [], [], '2026-10-28', allowed=set())
        self.assertEqual(c[0]['carried_note'], 'Not re-confirmed since 2026-10-28 – call before you go')

    def test_reconfirmed_venue_drops_the_label(self):
        first, _, _ = C.carry_items([V], [], [], '2026-10-28', allowed=set())
        again, carried, _ = C.carry_items(first, [dict(V, last_verified='2026-10-29')], [], '2026-10-29', allowed=set())
        self.assertEqual(carried, []); self.assertNotIn('call_check', again[0]); self.assertNotIn('carried_since', again[0])


class RunId(unittest.TestCase):
    def test_run_id_shapes(self):
        with mock.patch.dict(os.environ, {}, clear=True): self.assertIsNone(C.run_id())
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '777'}, clear=True): self.assertEqual(C.run_id(), '777.1')
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '2'}, clear=True): self.assertEqual(C.run_id(), '777.2')
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '777', 'REFRESH_RUN_ID': 'local-1'}, clear=True): self.assertEqual(C.run_id(), 'local-1')


class _FakeDate(datetime.date):
    @classmethod
    def today(cls): return cls(2027, 3, 1)


class GuardMidnight(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(os.path.join(self.d, 'logs')); os.makedirs(os.path.join(self.d, 'overrides'))
        self.v = dict(V, verified_on='2026-11-01', last_verified='2027-02-20')
    def tearDown(self): shutil.rmtree(self.d)
    def log(self, run, env):
        with mock.patch.dict(os.environ, env, clear=True):
            C.write_log([], run, root=self.d, not_carried=[{'id': 'ww-v', 'name': 'Village Hall', 'why': 'closed'}])
    def guard(self, env, run_day='2027-03-01'):
        with mock.patch.dict(os.environ, env, clear=True):
            return G.guard('warmspaces', [self.v], [], run_day=run_day, root=self.d)

    def test_default_run_day_after_midnight_still_honours_the_same_run(self):
        """refresh_guard.main() passes no run_day: guard() takes today's date, which is the day after the build's log."""
        env = {'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '1'}
        self.log('2027-02-28', env)
        with mock.patch.object(G.datetime, 'date', _FakeDate):
            out, rep = self.guard(env, run_day=None)
        self.assertEqual(out, []); self.assertEqual(rep['not_restored'], [{'id': 'ww-v', 'why': 'closed'}])

    def test_a_rerun_attempt_does_not_trust_attempt_one_log(self):
        self.log('2027-03-01', {'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '1'})
        out, _ = self.guard({'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '2'})
        self.assertEqual([x['id'] for x in out], ['ww-v']); self.assertTrue(out[0]['call_check'])

    def test_log_without_run_id_falls_back_to_the_date(self):
        self.log('2027-03-01', {})
        self.assertEqual(self.guard({'GITHUB_RUN_ID': '777'})[0], [])                                   # same date: trusted
        self.assertEqual([x['id'] for x in self.guard({'GITHUB_RUN_ID': '777'}, '2027-03-02')[0]], ['ww-v'])   # other date: not

    def test_local_guard_with_a_ci_log_falls_back_to_the_date(self):
        self.log('2027-02-28', {'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '1'})
        self.assertEqual([x['id'] for x in self.guard({})[0]], ['ww-v'])   # 1 Mar locally vs a 28 Feb CI log: not trusted


if __name__ == '__main__': unittest.main()
