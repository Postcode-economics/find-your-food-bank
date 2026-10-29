"""29 Oct 2026: Cloudflare Bot Fight Mode answered the deploy wait's curl poll with a 403 challenge (cf-mitigated) on every
request from 27 Oct, so every deploy check read '' and failed as "deploy not live" with nothing tested. The live build is now
read in real Chrome via check_browser (scripts/live_build.py). Dean 29 Oct: a Cloudflare block (403 / cf-mitigated /
'Just a moment') must fail loudly as "Cloudflare blocked the live check", on push and in the daily check, never as "not live".

The workflow tests run the real step scripts from deploy-check.yml in bash, with alert.py, git and the revert replaced by echo."""
import http.server, os, re, subprocess, sys, tempfile, threading, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import live_build as L

Y = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml'), encoding='utf-8').read()
LIVE = Y[:Y.index('\n  tile-fallback:')]
TILE = Y[Y.index('\n  tile-fallback:'):]
CHALLENGE_HTML = ('<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title></head>'
                  '<body>helpmap.uk Performing security verification</body></html>')
SHA = 'c0ffee' * 6 + 'c0ff'


def step(job, start, end):
    return job[job.index(start):job.index(end, job.index(start))]


def run_block(job, marker):
    """The `run: |` script of the step at marker, dedented."""
    at = job.index(marker)
    at = job.index('run: |\n', at) + len('run: |\n')
    lines = []
    for line in job[at:].splitlines():
        if line.strip() and not line.startswith(' ' * 10):
            break
        lines.append(line[10:])
    return '\n'.join(lines) + '\n'


def expand(script, outcomes):
    def sub(m):
        expr = m.group(1).strip()
        if expr == 'github.sha':
            return SHA
        o = re.fullmatch(r'steps\.(\w+)\.outcome', expr)
        return outcomes.get(o.group(1), 'skipped') if o else ''
    return re.sub(r'\$\{\{(.*?)\}\}', sub, script)


def bash(script, env, cwd=R):
    p = subprocess.run(['bash', '-e', '-c', script], capture_output=True, text=True, env=dict(os.environ, **env), cwd=cwd)
    return p.returncode, p.stdout + p.stderr


def safe(script):
    """No alert, git, network or revert from a test: each is echoed instead."""
    script = script.replace('git ls-remote origin refs/heads/main | cut -f1', 'echo %s' % SHA)
    script = script.replace('python scripts/alert.py', 'echo ALERT')
    script = script.replace('bash scripts/revert_site.sh', 'echo REVERTED')
    return re.sub(r'(?m)(^|[;&|(]\s*|\$\()git ', r'\1echo git ', script)


class Fake(tempfile.TemporaryDirectory):
    """A fake live_build.py: the real classify() on what Cloudflare sends, exit code as the real script."""
    def __init__(self, status, cf, body):
        super().__init__()
        self.path = os.path.join(self.name, 'fake_live_build.py')
        open(self.path, 'w').write(
            'import sys; sys.path.insert(0, %r)\nimport live_build as L\n'
            'b, blocked, why = L.classify(%r, %r, %r)\nprint("poll 1/1: " + why, file=sys.stderr)\nprint(b)\n'
            'sys.exit(0 if b == "fyfb-v95" else (L.BLOCKED if blocked else 1))\n'
            % (os.path.join(R, 'scripts'), status, cf, body))

    def __enter__(self):
        return self


class Classify(unittest.TestCase):
    def test_build_read(self):
        self.assertEqual(L.classify(200, '', '{"build": "fyfb-v95"}')[:2], ('fyfb-v95', False))

    def test_cloudflare_blocks_are_named(self):
        for status, cf, text in ((403, 'challenge', CHALLENGE_HTML), (403, '', 'error code: 1020'), (None, '', CHALLENGE_HTML),
                                 (200, 'challenge', '')):
            build, blocked, why = L.classify(status, cf, text)
            self.assertEqual((build, blocked), ('', True), (status, cf))
            self.assertIn('Cloudflare blocked the live check', why)

    def test_other_failures_are_not_a_block(self):
        for status, text in ((404, 'Not Found'), (500, ''), (200, '<html>old page</html>'), (None, '')):
            build, blocked, _ = L.classify(status, '', text)
            self.assertEqual((build, blocked), ('', False), (status, text))

    def test_check_output_scan(self):
        self.assertTrue(L.blocked_in_log('PASS a\nFAIL 3dc505a65 ios / bot page instead of the site (Just a moment...)\n'))
        self.assertTrue(L.blocked_in_log('AssertionError: blocked or challenged page (Just a moment...)'))
        self.assertFalse(L.blocked_in_log('retry: blocked or challenged (bot page instead of the site (Just a moment...))\nPASS a'))
        self.assertFalse(L.blocked_in_log('FAIL 3dc505a65 ios / pins 0, items 0, map false'))

    def test_exit_codes(self):
        self.assertEqual(L.BLOCKED, 3)
        self.assertEqual(L.main(['live_build.py']), 1)


class ChallengeIsReportedNotNotLive(unittest.TestCase):
    """The step scripts from deploy-check.yml, run in bash on a Cloudflare challenge."""

    def wait(self, job, marker, fake):
        script = safe(expand(run_block(job, marker), {}))
        script = script.replace('python scripts/live_build.py https://helpmap.uk', 'python %s https://helpmap.uk' % fake.path)
        script = re.sub(r'curl [^\n]*?(2>&1 \|\| true\))', r'echo "HTTP/2 403"; echo "cf-mitigated: challenge" \1', script)
        script = script.replace('python -c', '%s -c' % sys.executable).replace('python %s' % fake.path, '%s %s' % (sys.executable, fake.path))
        with tempfile.NamedTemporaryFile('r', suffix='.env') as ge:
            code, out = bash(script, {'GITHUB_ENV': ge.name})
            return code, out, ge.read()

    def test_wait_steps_report_a_challenge_as_cloudflare(self):
        for job, marker, notlive in ((LIVE, 'id: wait', 'so the live checks did not run'),
                                     (TILE, 'name: Wait for the deploy', 'so the fallback check did not run')):
            with Fake(403, 'challenge', CHALLENGE_HTML) as fake:
                code, out, env = self.wait(job, marker, fake)
            self.assertEqual(code, 1, out)
            self.assertIn('::error::Cloudflare blocked the live check', out)
            self.assertIn('cf-mitigated: challenge', out)  # curl's answer is shown, not discarded
            self.assertNotIn('this commit is not live', out)
            self.assertIn('CF_BLOCKED=deploy-wait', env)
            with Fake(200, '', '{"build": "fyfb-v94"}') as fake:  # an old build is still "not live", not Cloudflare
                code, out, env = self.wait(job, marker, fake)
            self.assertEqual(code, 1, out)
            self.assertIn('this commit is not live, ' + notlive, out)
            self.assertNotIn('Cloudflare blocked', out)
            self.assertNotIn('CF_BLOCKED', env)
            with Fake(200, '', '{"build": "fyfb-v95"}') as fake:
                code, out, env = self.wait(job, marker, fake)
            self.assertEqual(code, 0, out)

    def alert(self, marker, outcomes, cf_blocked):
        script = safe(expand(run_block(LIVE, marker), outcomes))
        env = {'GITHUB_SERVER_URL': 'https://github.com', 'GITHUB_REPOSITORY': 'x/y', 'GITHUB_RUN_ID': '1'}
        if cf_blocked:
            env['CF_BLOCKED'] = cf_blocked
        return bash(script, env, cwd=tempfile.mkdtemp())

    def test_push_alert_names_cloudflare_and_never_reverts(self):
        code, out = self.alert('Revert the deploying commit', {'install': 'success', 'wait': 'failure'}, 'deploy-wait')
        self.assertEqual(code, 1, out)
        self.assertIn('ALERT open old-links Cloudflare blocked the live check (deploy-wait) - NOT reverted', out)
        self.assertNotIn('Deploy not live', out)
        self.assertNotIn('REVERTED', out)
        code, out = self.alert('Revert the deploying commit', {'install': 'success', 'wait': 'failure'}, '')
        self.assertIn('ALERT open old-links Deploy not live after 10 min', out)  # a real "not live" keeps its own alert

    def test_daily_alert_names_cloudflare(self):
        code, out = self.alert('- name: Alert (daily check)', {'install': 'success', 'wait': 'failure'}, 'deploy-wait')
        self.assertEqual(code, 1, out)
        self.assertIn('ALERT open old-links Cloudflare blocked the live check (daily: deploy-wait)', out)
        self.assertNotIn('Daily live check failed', out)

    def test_a_block_during_the_checks_is_found_and_named(self):
        tmp = tempfile.mkdtemp()
        open(os.path.join(tmp, 'live-old-links.log'), 'w').write(
            'PASS 3dc505a65 ios / pins 21\nFAIL 3dc505a65 android / bot page instead of the site (Just a moment...)\n')
        open(os.path.join(tmp, 'live-journeys.log'), 'w').write('retry: blocked or challenged (x)\nFAIL search: no results\n')
        script = expand(run_block(LIVE, 'id: cf'), {'wait': 'success', 'oldlinks': 'failure', 'journeys': 'failure'})
        script = script.replace('python scripts/live_build.py', '%s scripts/live_build.py' % sys.executable)
        with tempfile.NamedTemporaryFile('r', suffix='.env') as ge:
            code, out = bash(script, {'GITHUB_ENV': ge.name, 'RUNNER_TEMP': tmp})
            env = ge.read()
        self.assertEqual(code, 0, out)
        self.assertIn('CF_BLOCKED=old-links\n', env)  # journeys failed for itself (its block was cleared by the retry)
        self.assertIn('::error::Cloudflare blocked the live check (old-links)', out)
        code, out = self.alert('Revert the deploying commit', {'install': 'success', 'wait': 'success', 'oldlinks': 'failure'}, 'old-links')
        self.assertIn('ALERT open old-links Cloudflare blocked the live check (old-links) - NOT reverted', out)
        self.assertNotIn('REVERTED', out)


class Wiring(unittest.TestCase):
    def test_both_waits_read_the_build_in_real_chrome(self):
        for job, end in ((LIVE, 'id: oldlinks'), (TILE, 'id: fallback')):
            wait = step(job, 'Wait for the deploy', end)
            self.assertIn('python scripts/live_build.py https://helpmap.uk "$want"', wait)
            self.assertNotRegex(wait, r'for i in \$\(seq')  # no curl poll
            self.assertIn('SUPERSEDED=1', wait)
        src = open(os.path.join(R, 'scripts', 'live_build.py'), encoding='utf-8').read()
        for k in ('import check_browser as B', 'B.new_context(', 'B.goto(', 'google-chrome'):
            self.assertIn(k, src)

    def test_playwright_is_installed_before_the_wait(self):
        for job in (LIVE, TILE):
            self.assertLess(job.index('python -m playwright install'), job.index('Wait for the deploy'))
        self.assertNotIn('playwright install', step(LIVE, 'id: oldlinks', 'id: journeys'))

    def test_curl_errors_are_not_discarded(self):
        for line in Y.splitlines():
            if re.search(r'\bcurl -', line):
                self.assertNotIn('2>/dev/null', line)
                self.assertNotIn('-fsS', line)

    def test_check_output_is_kept_for_the_scan(self):
        for sid, name in (('oldlinks', 'old-links'), ('journeys', 'journeys'), ('designlock', 'design-lock'), ('darkdefault', 'dark-default')):
            s = step(LIVE, 'id: %s' % sid, '- id:' if sid != 'darkdefault' else '- id: cf')
            self.assertIn('set -o pipefail;', s)  # tee must not hide the check's own exit code
            self.assertIn('tee "$RUNNER_TEMP/live-%s.log"' % name, s)
        self.assertLess(LIVE.index('id: cf'), LIVE.index('Revert the deploying commit'))

    def test_install_failure_alerts_and_never_reverts(self):
        push = step(LIVE, 'Revert the deploying commit', '- name: Alert (daily check)')
        i = push.index('if [ "$failed" = "install" ]')
        self.assertLess(i, push.index('revert_site.sh'))
        self.assertIn('exit 1', push[i:push.index('\n          fi', i)])

    def test_daily_run_uses_the_same_wait(self):
        self.assertIn('cron: "15 6 * * *"', Y)
        wait = step(LIVE, 'id: wait', 'id: oldlinks')
        self.assertNotRegex(wait.split('run: |', 1)[0], r'\bif:')  # the wait runs on push and on the schedule alike


class _Challenge(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = CHALLENGE_HTML.encode()
        self.send_response(403)
        self.send_header('content-type', 'text/html; charset=UTF-8')
        self.send_header('cf-mitigated', 'challenge')
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class RealChromeOnAChallenge(unittest.TestCase):
    """live_build.py in real Chrome against a local stand-in for Cloudflare's 403 challenge (no network)."""

    def test_challenge_page_is_detected_and_reported(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            self.skipTest('playwright not installed')
        if not L.chrome_path():
            self.skipTest('no google-chrome')
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Challenge)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            p = subprocess.run([sys.executable, os.path.join(R, 'scripts', 'live_build.py'),
                                'http://127.0.0.1:%d' % srv.server_address[1], 'fyfb-v95', '2', '0'],
                               capture_output=True, text=True, timeout=120)
        finally:
            srv.shutdown()
        self.assertEqual(p.returncode, L.BLOCKED, p.stderr)
        self.assertEqual(p.stdout.strip(), '')
        self.assertIn('Cloudflare blocked the live check (HTTP 403, cf-mitigated: challenge)', p.stderr)
        self.assertIn('::warning::Cloudflare blocked the live check on 2 of 2 polls', p.stderr)


if __name__ == '__main__':
    unittest.main()
