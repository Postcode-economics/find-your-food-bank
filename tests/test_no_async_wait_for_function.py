"""Guard for the test_sw_cache_retry flake (data.js net::ERR_EMPTY_RESPONSE).

Cause: Playwright's wait_for_function does not await a Promise. An `async` predicate returns a
Promise, which is truthy, so the wait returned at once. The test then blocked data.js and leaflet.js
before sw.js had finished precaching them, the worker had nothing to fall back to, and the page saw
ERR_EMPTY_RESPONSE. The fix (7d83e9e) polls with page.evaluate, which does await. This stops the
same pattern coming back in any test or check script.
"""
import os, re, unittest

R = os.path.join(os.path.dirname(__file__), '..')
PAT = re.compile(r'wait_for_function\(\s*(?:[rubf]*)("""|\'\'\'|"|\')\s*async\b', re.S)


class NoAsyncWaitForFunction(unittest.TestCase):
    def test_pattern_is_caught(self):
        self.assertTrue(PAT.search('page.wait_for_function(\n  """async (n) => true""")'))
        self.assertFalse(PAT.search('page.wait_for_function("() => window.ok")'))

    def test_no_async_predicate_passed_to_wait_for_function(self):
        bad = []
        for d in ('tests', 'scripts'):
            for root, _, files in os.walk(os.path.join(R, d)):
                for f in files:
                    if f.endswith('.py') and f != os.path.basename(__file__):
                        p = os.path.join(root, f)
                        src = open(p, encoding='utf-8').read()
                        for m in PAT.finditer(src):
                            bad.append('%s:%d' % (os.path.relpath(p, R), src.count('\n', 0, m.start()) + 1))
        self.assertEqual(bad, [], 'wait_for_function does not await an async predicate; poll with evaluate instead')


if __name__ == '__main__':
    unittest.main()
