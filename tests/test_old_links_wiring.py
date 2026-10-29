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
    def test_ci_shards_cover_every_case_once(self):
        try: import playwright  # noqa: F401  (old_links imports it at the top)
        except ImportError: self.skipTest('playwright not installed')
        import sys; sys.path.insert(0, os.path.join(R, 'scripts')); import old_links
        j = json.loads(rd('scripts', 'old_links.json'))
        allc = old_links.cases()
        self.assertEqual(len(allc), len(old_links.OLD_COMMITS) * len(j['sent'] + j['variants']) * len(old_links.UAS))
        self.assertEqual(len(set(allc)), len(allc))
        self.assertEqual(old_links.shard(''), allc)  # unsharded (deploy check, daily): every case
        y = rd('.github', 'workflows', 'tests.yml')
        n = int(y.split('OLD_LINKS_SHARD: ${{ matrix.shard }}/', 1)[1].split()[0])
        self.assertIn('shard: [%s]' % ', '.join(str(k) for k in range(1, n + 1)), y)
        parts = [old_links.shard('%d/%d' % (k, n)) for k in range(1, n + 1)]
        self.assertEqual(sorted(c for p in parts for c in p), sorted(allc))
        self.assertLessEqual(max(map(len, parts)) - min(map(len, parts)), 1)
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
