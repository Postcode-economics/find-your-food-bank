"""Self-learning part 2 (Dean, 25 Oct 2026): corrections, change signals, trust/agreement, season, demand, visitor,
weekly self-review (bounded), accuracy trend, digest. Order of checks only - never map data."""
import os, sys, json, tempfile, shutil, datetime, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
import learning, learning_signals as LS

def site(d, items, state, extra=None):
    for s in ('reports', 'overrides', 'logs'): os.makedirs(os.path.join(d, s), exist_ok=True)
    open(os.path.join(d, 'data.full.js'), 'w').write('window.FB_DATA=' + json.dumps({'items': items}) + ';')
    json.dump(state, open(os.path.join(d, 'reports', 'full_check_state.json'), 'w'))
    for k, v in (extra or {}).items(): json.dump(v, open(os.path.join(d, k), 'w'))

class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.old = (LS.ROOT, LS.OUT, LS.MD, learning.STATE)
        LS.ROOT = self.d; LS.OUT = os.path.join(self.d, 'reports', 'learning_signals.json'); LS.MD = os.path.join(self.d, 'reports', 'learning_review.md')
        learning.STATE = os.path.join(self.d, 'reports', 'learning_state.json')
    def tearDown(self):
        LS.ROOT, LS.OUT, LS.MD, learning.STATE = self.old; shutil.rmtree(self.d)
    def items(self):
        return [dict(id='a', type='foodbank', givefood='g', website='https://a.org/', tel='01234567890'),
                dict(id='b', type='foodbank', givefood='g', website='https://b.org/', tel='01111111111'),
                dict(id='ifan-c', type='foodbank', website='https://c.org/', tel='02222222222')]
    def state(self):
        return {'sites': {'https://a.org/': {'phones': ['01234567890'], 'fail_runs': 0},
                          'https://b.org/': {'phones': ['09999999999'], 'fail_runs': 0},
                          'https://c.org/': {'phones': [], 'fail_runs': 3, 'closed': ''}}}
    def test_signals_trust_and_corrections(self):
        site(self.d, self.items(), self.state(), {'overrides/phones.json': {'ifan-c': '02222222222'}, 'overrides/opening_times.json': {'a': {}, 'b': {}}})
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertIn('https://c.org/', o['signals']); self.assertIn('dead link', o['signals']['https://c.org/'][0])
        self.assertEqual(o['correction_rate'].get('Give Food'), 0.0)   # opening_times.json is automated, not a correction
        self.assertGreater(o['correction_rate']['IFAN'], 0)
        self.assertEqual(o['agreement_n']['Give Food'], 2); self.assertAlmostEqual(o['trust']['Give Food'], 0.5)  # (1+1)/(2+2)
        self.assertIn('signal', o['why']['https://b.org/'])   # stored phone not on own site
        self.assertIn('no visitor data yet', o['demand_note']); self.assertNotIn('demand', str(o['why']))
    def test_no_map_data_written(self):
        site(self.d, self.items(), self.state()); before = open(os.path.join(self.d, 'data.full.js')).read()
        LS.write(LS.build(datetime.date(2026, 10, 26)))
        self.assertEqual(open(os.path.join(self.d, 'data.full.js')).read(), before)
        self.assertTrue(os.path.exists(LS.MD)); self.assertIn('What the system learned', open(LS.MD).read())
    def test_weights_bounded(self):
        w = dict(LS.DEFAULT_W)
        for _ in range(50): w = LS.weights(w, {k: 1 for k in LS.DEFAULT_W})
        for k, b in LS.DEFAULT_W.items(): self.assertLessEqual(w[k], b * LS.HI + 1e-9)
        for _ in range(80): w = LS.weights(w, {k: -1 for k in LS.DEFAULT_W})
        for k, b in LS.DEFAULT_W.items(): self.assertGreaterEqual(w[k], b * LS.LO - 1e-9)
        w2 = LS.weights(dict(LS.DEFAULT_W), {'signal': 1}); self.assertAlmostEqual(w2['signal'], LS.DEFAULT_W['signal'] * 1.1)
    def test_demand_and_visitor_used_when_present(self):
        site(self.d, self.items(), self.state(), {'reports/demand.json': {'a': 100, 'b': 1}, 'overrides/visitor_reports.json': {'b': [{'when': '2026-10-25', 'what': 'closed'}]}})
        o = LS.build(datetime.date(2026, 10, 26))
        self.assertGreater(o['why']['https://a.org/']['demand'], o['why']['https://b.org/'].get('demand', 0))
        self.assertIn('visitor', o['why']['https://b.org/'])
    def test_boost_changes_order_and_ends_rest(self):
        s = learning.load(os.devnull); today = '2026-10-26'
        for k in ('x', 'y'): learning.record(s, k, today, True)
        order, _, _ = learning.plan(s, ['x', 'y'], today, boosts={'y': 1.0}); self.assertEqual(order[0], 'y')
        for _ in range(3): learning.record(s, 'z', today, False)
        _, skipped, _ = learning.plan(s, ['z'], today); self.assertIn('z', skipped)
        _, skipped, _ = learning.plan(s, ['z'], today, boosts={'z': 1.0}); self.assertNotIn('z', skipped)
    def test_trend_weekly(self):
        tr = [{'day': '2026-10-19', 'reachable': 0.9, 'phone_agreement': 0.8, 'corrections': 5}, {'day': '2026-10-26', 'reachable': 0.95, 'phone_agreement': None, 'corrections': 6}]
        wk = LS.weekly(tr); self.assertEqual(len(wk), 2); self.assertEqual(wk[0][0], '2026-W43')
    def test_wired(self):
        self.assertIn('learning_signals.boosts()', open(os.path.join(R, 'scripts', 'full_check.py')).read())
        self.assertIn('learning_signals', open(os.path.join(R, 'scripts', 'digest.py')).read())
        self.assertIn('scripts/learning_signals.py', open(os.path.join(R, '.github', 'workflows', 'refresh.yml')).read())
if __name__ == '__main__': unittest.main()
