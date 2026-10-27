"""Guard for the test_sw_cache_retry race (27 Oct 2026).

Playwright's wait_for_function does not await a Promise: an async predicate returns a Promise, which is
truthy, so the wait ends at once. test_sw_cache_retry used one to wait for sw.js to finish precaching,
blocked the network while the worker was still installing, and failed at random in CI with
data.js net::ERR_EMPTY_RESPONSE (16 of 30 local runs on main's code with that old wait).
No browser check may use an async predicate with wait_for_function, and until() must only accept a real True.
"""
import glob, os, re, sys, unittest

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ASYNC_WAIT = re.compile(r"wait_for_function\(\s*[rbuRB]?(\"\"\"|'''|\"|')\s*(async\b|\(?\s*\)?\s*=>\s*(caches|navigator\.serviceWorker\.getRegistration)\b)", re.S)


class T(unittest.TestCase):
    def test_no_async_predicate_in_wait_for_function(self):
        hits = []
        for f in sorted(glob.glob(os.path.join(R, 'tests', '*.py')) + glob.glob(os.path.join(R, 'scripts', '*.py'))):
            if os.path.basename(f) == os.path.basename(__file__):
                continue
            with open(f, encoding='utf-8') as fh:
                src = fh.read()
            for m in ASYNC_WAIT.finditer(src):
                hits.append('%s:%d' % (os.path.relpath(f, R), src.count('\n', 0, m.start()) + 1))
        self.assertEqual(hits, [], 'wait_for_function with an async predicate returns at once; poll with evaluate instead')

    def test_the_regex_catches_the_old_race(self):
        old = 'page.wait_for_function(\n    """async (name) => {\n const reg = 1; }""", arg=cache)'
        self.assertTrue(ASYNC_WAIT.search(old))
        self.assertFalse(ASYNC_WAIT.search('pg.wait_for_function("!!(navigator.serviceWorker&&navigator.serviceWorker.controller)")'))

    def test_until_needs_a_real_true(self):
        import test_sw_cache_retry as S

        class Page:
            def __init__(self, values):
                self.values = list(values)

            def evaluate(self, js, arg=None):
                return self.values.pop(0) if self.values else {}

        # A Promise comes back as {} through evaluate; truthy values other than True are not a pass.
        with self.assertRaises(AssertionError):
            S.until(Page([{}, 'x', 1, [1]]), 'async () => true', timeout=1500)
        S.until(Page([False, True]), 'async () => true', timeout=3000)


if __name__ == '__main__':
    unittest.main()
