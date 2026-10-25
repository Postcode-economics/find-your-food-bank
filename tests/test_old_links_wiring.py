"""Old-links check is wired into CI, post-deploy (with revert) and daily; the service worker never navigates pages (25 Oct 11:29 bug)."""
import json, os, unittest
R = os.path.join(os.path.dirname(__file__), '..')
rd = lambda *p: open(os.path.join(R, *p), encoding='utf-8').read()
class T(unittest.TestCase):
    def test_wiring(self):
        self.assertIn('python scripts/old_links.py\n', rd('.github', 'workflows', 'tests.yml'))
        d = rd('.github', 'workflows', 'deploy-check.yml')
        for k in ('python scripts/old_links.py https://helpmap.uk', 'git revert --no-edit', 'cron: "15 6 * * *"'): self.assertIn(k, d)
    def test_links_listed(self):
        j = json.loads(rd('scripts', 'old_links.json'))
        for k in ('/', '/?q=SM1%201AA', '/food-banks/'): self.assertIn(k, j['sent'])
        self.assertTrue(any('igsh' in v for v in j['variants']) and any('fbclid' in v for v in j['variants']) and any('utm_' in v for v in j['variants']))
    def test_sw_never_navigates_clients(self):
        self.assertNotIn('.navigate(', rd('sw.js'))
    def test_boot_watchdog(self):
        h = rd('index.html'); self.assertIn("var k='hmBoot'", h); self.assertIn("k='hmHeal'", h)
