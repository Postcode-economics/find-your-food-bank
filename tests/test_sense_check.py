"""'Does the result make sense?' suite (owner, 25 Oct 2026). Runs scripts/sense_check.py in CI when a browser is available;
the refresh workflows also run it after the publish gate, and a failure stops publishing."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(R, 'scripts'))
class Static(unittest.TestCase):
    def test_searches_and_wiring(self):
        import sense_check as S
        qs = [q for q, _ in S.SEARCHES]
        for q in ('Littlehampton', 'Suffolk', 'Kent', 'Devon', 'West Sussex', 'Fife', 'Manchester', 'Cardiff', 'Belfast'): self.assertIn(q, qs)
        import json; names = {a['name'] for a in json.load(open(os.path.join(R, 'counties.json')))['areas']}
        for _, a in S.SEARCHES: self.assertIn(a, names)
        for f in ('refresh.yml', 'refresh-shelters.yml', 'refresh-warmspaces.yml'):
            self.assertIn('scripts/sense_check.py', open(os.path.join(R, '.github', 'workflows', f)).read(), f)
class Browser(unittest.TestCase):
    def test_sense(self):
        try: import playwright  # noqa
        except Exception: raise unittest.SkipTest('playwright not installed')
        import sense_check as S
        if not S.reachable(): raise unittest.SkipTest('postcodes.io unreachable')
        chrome = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None
        try: f, rows = S.run(chrome=chrome)
        except Exception as e:
            if 'Executable doesn' in str(e): raise unittest.SkipTest('no browser installed')
            raise
        self.assertEqual(f, [], '\n'.join(f[:20]))
if __name__ == '__main__': unittest.main()
