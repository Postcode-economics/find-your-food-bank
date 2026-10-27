import os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import privacy_check as p


class PrivacyLive(unittest.TestCase):
    def test_ua_matches_cloudflare_skip_rule(self):
        self.assertIn('helpmap-check', p.UA)

    def test_unfetchable_live_url_still_fails(self):
        with mock.patch.object(p, '_get', side_effect=OSError('x')), \
             mock.patch.dict(os.environ, {'PRIVATE_BLOCKLIST': 'zz-test-needle-not-real'}):
            self.assertEqual(p.main(['--live']), 1)

    def test_retry_then_success(self):
        calls = []
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'ok'
        def fake(req, timeout=30):
            calls.append(1)
            if len(calls) < 2: raise OSError('transient')
            return R()
        with mock.patch('urllib.request.urlopen', fake), mock.patch('time.sleep'):
            self.assertEqual(p._get('https://helpmap.uk/'), 'ok')


if __name__ == '__main__':
    unittest.main()
