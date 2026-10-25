"""Old-links check is wired into CI, post-deploy (with revert) and daily; the service worker never navigates pages (25 Oct 11:29 bug)."""
import json, os, unittest
R = os.path.join(os.path.dirname(__file__), '..')
rd = lambda *p: open(os.path.join(R, *p), encoding='utf-8').read()
class T(unittest.TestCase):
    def test_wiring(self):
        self.assertIn('python scripts/old_links.py\n', rd('.github', 'workflows', 'tests.yml'))
        d = rd('.github', 'workflows', 'deploy-check.yml')
        for k in ('python scripts/old_links.py https://helpmap.uk', 'bash scripts/revert_site.sh', 'cron: "15 6 * * *"'): self.assertIn(k, d)
    def test_links_listed(self):
        j = json.loads(rd('scripts', 'old_links.json'))
        for k in ('/', '/?q=SM1%201AA', '/food-banks/'): self.assertIn(k, j['sent'])
        self.assertTrue(any('igsh' in v for v in j['variants']) and any('fbclid' in v for v in j['variants']) and any('utm_' in v for v in j['variants']))
    def test_sw_never_navigates_clients(self):
        self.assertNotIn('.navigate(', rd('sw.js'))
    def test_boot_watchdog(self):
        h = rd('index.html'); self.assertIn("var k='hmBoot'", h); self.assertIn("k='hmHeal'", h)

class RevertSite(unittest.TestCase):
    def test_reverts_site_files_only(self):
        import subprocess, tempfile, shutil
        d = tempfile.mkdtemp(); sh = lambda c: subprocess.run(c, shell=True, cwd=d, check=True, capture_output=True, text=True).stdout
        try:
            sh('git init -q && git config user.email t@t && git config user.name t && mkdir -p .github/workflows && echo a>index.html && echo w1>.github/workflows/x.yml && echo k>keep.js && git add -A && git commit -qm base')
            sh('echo b>index.html && echo w2>.github/workflows/x.yml && echo n>new.js && git rm -q keep.js && git add -A && git commit -qm bad')
            sha = sh('git rev-parse HEAD').strip()
            sh('bash %s %s' % (os.path.join(R, 'scripts', 'revert_site.sh'), sha))
            self.assertEqual(open(os.path.join(d, 'index.html')).read(), 'a\n')
            self.assertEqual(open(os.path.join(d, '.github', 'workflows', 'x.yml')).read(), 'w2\n')   # workflow untouched
            self.assertFalse(os.path.exists(os.path.join(d, 'new.js'))); self.assertTrue(os.path.exists(os.path.join(d, 'keep.js')))
            self.assertNotIn('.github', sh('git show --name-only --format= HEAD'))
        finally: shutil.rmtree(d)
    def test_wait_step_tolerates_unreachable(self):
        d = rd('.github', 'workflows', 'deploy-check.yml'); self.assertIn('|| true)', d)
