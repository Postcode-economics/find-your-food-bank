"""journeys.scenario: one retry for a clean timeout; never retries away a recorded failed check."""
import os, sys, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import journeys as J

class T(unittest.TestCase):
    def setUp(self): J.scenario.deadline = time.time() + 600; J.shot = lambda *a: None
    def run_seq(self, steps):
        r = J.R(); it = iter(steps)
        def body(box):
            kind = next(it)
            if kind == 'failcheck_then_raise': r.ok('J', 't', False, 'bad'); raise TimeoutError('slow')
            if kind == 'raise': raise TimeoutError('slow')
            r.ok('J', 't', True)
        J.scenario(r, 'J', 't', body); return r.res['J']
    def test_clean_timeout_retried(self): self.assertEqual(self.run_seq(['raise', 'pass'])['fail'], 0)
    def test_fail_then_timeout_not_hidden(self): self.assertGreaterEqual(self.run_seq(['failcheck_then_raise', 'pass'])['fail'], 1)
    def test_two_timeouts_fail(self): self.assertEqual(self.run_seq(['raise', 'raise'])['fail'], 1)

if __name__ == '__main__': unittest.main()
