"""Sharded CI jobs (Dean 28 Oct 2026) must still run every test exactly once, and the gate must notice if not."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import shard

Y = open(os.path.join(R, '.github', 'workflows', 'tests.yml'), encoding='utf-8').read()


def job(name):
    body = Y.split('\n  %s:\n' % name, 1)[1]
    m = re.search(r'\n  [A-Za-z0-9-]+:\n', body)
    return body[:m.start()] if m else body


class Split(unittest.TestCase):
    CASES = ['tests/test_%02d.py::T::test_%d' % (m, k) for m in range(23) for k in range(m % 4 + 1)]
    module = staticmethod(lambda c: c.split('::')[0])

    def test_unset_runs_everything_in_order(self):
        self.assertEqual(shard.pick(self.CASES, env={}), self.CASES)

    def test_shards_cover_every_case_exactly_once_and_keep_modules_whole(self):
        for n in (1, 2, 3, 4, 7):
            got = [shard.pick(self.CASES, group=self.module, env={'HELPMAP_SHARD': '%d/%d' % (i, n)}) for i in range(1, n + 1)]
            flat = [c for g in got for c in g]
            self.assertEqual(sorted(flat), sorted(self.CASES), n)
            for g in got:
                self.assertEqual(g, [c for c in self.CASES if c in g])   # original order kept
            owner = {}
            for i, g in enumerate(got):
                for c in g:
                    self.assertEqual(owner.setdefault(self.module(c), i), i, 'module split across shards')

    def test_weights_balance_the_load(self):
        w = {'a': 100, 'b': 60, 'c': 40, 'd': 30, 'e': 30}
        a = shard.assign(list(w), 2, w)
        load = [sum(v for k, v in w.items() if a[k] == s) for s in (1, 2)]
        self.assertEqual(sorted(load), [130, 130])

    def test_bad_spec_is_refused(self):
        for v in ('0/4', '5/4', '1/0', 'x'):
            with self.assertRaises(ValueError):
                shard.spec({'HELPMAP_SHARD': v})


class Verify(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.full = ['a', 'b', 'c', 'd', 'e']

    def tearDown(self):
        shutil.rmtree(self.d)

    def rep(self, i, n, picked, ran=None, expected=None, suite='s'):
        json.dump(dict(suite=suite, shard=i, of=n, expected=expected or self.full, picked=picked, ran=picked if ran is None else ran),
                  open(os.path.join(self.d, '%s-%d.json' % (suite, i)), 'w'))

    def test_complete(self):
        self.rep(1, 2, ['a', 'c', 'e']); self.rep(2, 2, ['b', 'd'])
        self.assertEqual(shard.verify('s', 2, self.d), [])

    def test_missing_shard_report(self):
        self.rep(1, 2, ['a', 'c', 'e'])
        self.assertTrue(any('no report' in p for p in shard.verify('s', 2, self.d)))

    def test_case_run_nowhere(self):
        self.rep(1, 2, ['a', 'c']); self.rep(2, 2, ['b', 'd'])
        self.assertTrue(any('ran in no shard' in p for p in shard.verify('s', 2, self.d)))

    def test_case_run_twice(self):
        self.rep(1, 2, ['a', 'b', 'c', 'e']); self.rep(2, 2, ['b', 'd'])
        self.assertTrue(any('more than one shard' in p for p in shard.verify('s', 2, self.d)))

    def test_picked_but_not_run(self):
        self.rep(1, 2, ['a', 'c', 'e'], ran=['a', 'c']); self.rep(2, 2, ['b', 'd'])
        self.assertTrue(any('did not run' in p for p in shard.verify('s', 2, self.d)))

    def test_shards_collected_different_lists(self):
        self.rep(1, 2, ['a', 'c', 'e']); self.rep(2, 2, ['b', 'd'], expected=['b', 'd'])
        self.assertTrue(any('different case list' in p for p in shard.verify('s', 2, self.d)))

    def test_other_suites_ignored(self):
        self.rep(1, 2, ['a', 'c', 'e']); self.rep(2, 2, ['b', 'd']); self.rep(1, 1, ['x'], suite='other')
        self.assertEqual(shard.verify('s', 2, self.d), [])


class PytestPlugin(unittest.TestCase):
    """tests/conftest.py: a real pytest run, split in 3, runs the same tests as the unsharded run."""
    def test_three_shards_equal_one_run(self):
        d = tempfile.mkdtemp()
        try:
            t = os.path.join(d, 'tests'); os.makedirs(os.path.join(t))
            shutil.copy(os.path.join(R, 'tests', 'conftest.py'), t)
            os.makedirs(os.path.join(d, 'scripts')); shutil.copy(os.path.join(R, 'scripts', 'shard.py'), os.path.join(d, 'scripts'))
            for m in range(5):
                open(os.path.join(t, 'test_m%d.py' % m), 'w').write(
                    'import unittest\nclass T(unittest.TestCase):\n' + ''.join('    def test_%d(self): pass\n' % k for k in range(m + 1))
                    + ('    @unittest.skip("x")\n    def test_skip(self): pass\n' if m == 2 else ''))
            run = lambda env: subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'], cwd=d,
                                             env=dict(os.environ, **env), capture_output=True, text=True)
            base = run({'HELPMAP_SHARD': ''})
            self.assertEqual(base.returncode, 0, base.stdout + base.stderr)
            self.assertIn('15 passed, 1 skipped', base.stdout)
            for i in (1, 2, 3):
                p = run({'HELPMAP_SHARD': '%d/3' % i, 'HELPMAP_SHARD_SUITE': 'demo'})
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(shard.verify('demo', 3, os.path.join(d, 'logs', 'shards')), [])
            ran = sorted(c for i in (1, 2, 3) for c in json.load(open(os.path.join(d, 'logs', 'shards', 'demo-%d.json' % i)))['ran'])
            self.assertEqual(len(ran), 16)
        finally:
            shutil.rmtree(d)


class Wiring(unittest.TestCase):
    """Each sharded job has a gate under the old job name that fails unless every shard passed and covered everything."""
    SHARDED = (('browser-tests', 'browser-tests-all', 'browser', 4), ('old-links', 'old-links-all', 'oldlinks', 3),
               ('iphone-webkit', 'iphone-webkit-all', 'webkit', 2), ('journeys', 'journeys-all', 'journeys', 2))

    def test_matrix_and_gate(self):
        for shard_job, gate, suite, n in self.SHARDED:
            s, g = job(shard_job), job(gate)
            self.assertIn('name: %s\n' % shard_job, g, gate)   # the gate keeps the old check name
            self.assertIn('shard: [%s]' % ', '.join(str(i) for i in range(1, n + 1)), s, shard_job)
            self.assertIn('fail-fast: false', s, shard_job)
            self.assertIn("HELPMAP_SHARD: ${{ matrix.shard }}/%d" % n, s, shard_job)
            self.assertIn('logs/shards/%s-${{ matrix.shard }}.json' % suite, s, shard_job)
            self.assertIn('needs: [changes, %s]' % shard_job, g, gate)
            self.assertIn("needs.%s.result" % shard_job, g, gate)
            self.assertIn('scripts/shard.py verify %s %d shards' % (suite, n), g, gate)
            for bad in ('continue-on-error', '--ignore', '-k ', '--deselect', 'xfail'):
                self.assertNotIn(bad, s, shard_job)

    def test_suites_unchanged(self):
        self.assertIn('python -m pytest -q tests -rs', job('browser-tests'))
        self.assertIn('Chrome binary guard', job('browser-tests'))
        w = job('iphone-webkit')
        for f in ('test_iphone_responsive', 'test_iphone_map_fix', 'test_sw_tag_hash', 'test_webkit_instagram', 'test_iphone_freeze',
                  'test_iphone_vector_recover', 'test_iphone_decode', 'test_iphone_backup_map', 'test_phone_qa_28oct', 'test_motion_28oct_3',
                  'test_website_link'):
            self.assertIn('tests/%s.py' % f, w)
        self.assertIn('python scripts/old_links.py\n', job('old-links'))
        self.assertIn('python scripts/journeys.py', job('journeys'))
