"""Privacy paths stay out of refresh commits, and missing old_links.py history cannot revert a deploy."""
import contextlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import old_links as O


class Snapshots(unittest.TestCase):
    def test_missing_snapshot_is_explicit_before_archive(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(O, 'ROOT', directory):
            subprocess.run(['git', 'init', '-q', directory], check=True)
            with patch.object(O.tempfile, 'mkdtemp') as make:
                with self.assertRaisesRegex(O.SnapshotUnavailable, 'historical snapshot commit .* is missing'):
                    O.snapshot('0' * 40)
                make.assert_not_called()

    def test_missing_snapshot_exit_and_output_without_browser_or_raw_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            with patch.object(O, 'OLD_COMMITS', {'0' * 40: True}), patch.dict(os.environ, GITHUB_OUTPUT=str(output)):
                text = io.StringIO()
                with contextlib.redirect_stdout(text):
                    code = O.main()
            self.assertEqual(code, 3)
            self.assertEqual(output.read_text(), 'snapshot_missing=true\n')
            self.assertIn('automatic revert skipped', text.getvalue())
            self.assertNotIn('tar:', text.getvalue())
            self.assertNotIn('Traceback', text.getvalue())

    def test_available_snapshot_extracts_public_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(O, 'ROOT', directory):
            subprocess.run(['git', 'init', '-q', directory], check=True)
            Path(directory, 'index.html').write_text('public site')
            subprocess.run(['git', '-C', directory, 'add', 'index.html'], check=True)
            subprocess.run(['git', '-C', directory, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-qm', 'public snapshot'], check=True)
            snapshot = O.snapshot('HEAD')
            try:
                self.assertEqual(Path(snapshot, 'index.html').read_text(), 'public site')
            finally:
                shutil.rmtree(snapshot)

    def test_baselines_exist_and_keep_both_release_behaviours(self):
        self.assertEqual(set(O.OLD_COMMITS.values()), {True, False})
        for commit, build in zip(O.OLD_COMMITS, ('fyfb-v85', 'fyfb-v80')):
            O.require_snapshot(commit)
            worker = subprocess.check_output(['git', '-C', str(ROOT), 'show', commit + ':sw.js'], text=True)
            self.assertIn(build, worker)


class Privacy(unittest.TestCase):
    def test_ignore_rules_and_helper_keep_internal_paths_private(self):
        paths = ['__pycache__/x.pyc', 'logs/x.json', 'reports/x.md', 'docs/x.md', 'email/x.txt',
                 'google_log.md', 'held_google.json', 'progress.md', 'summary.md', 'HANDOFF-worker.md',
                 'logs/fetch_timing_shelters.json']
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '-q', directory], check=True)
            shutil.copyfile(ROOT / '.gitignore', Path(directory) / '.gitignore')
            for name in paths + ['public.json']:
                file = Path(directory, name)
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('{}')
            ignored = subprocess.run(['git', 'check-ignore', '--', *paths], cwd=directory, capture_output=True, text=True)
            self.assertEqual(ignored.returncode, 0, ignored.stderr)
            self.assertEqual(set(ignored.stdout.splitlines()), set(paths))
            result = subprocess.run(['bash', str(ROOT / 'scripts/git_add_existing.sh'), *paths, 'public.json'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            staged = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=directory, text=True)
            self.assertEqual(staged.splitlines(), ['public.json'])
            # The helper's automatic timing-file special case must also respect the ignore, with no arguments.
            subprocess.run(['git', 'rm', '-q', '--cached', 'public.json'], cwd=directory, check=True)
            result = subprocess.run(['bash', str(ROOT / 'scripts/git_add_existing.sh')], cwd=directory, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=directory), b'')


class DeployRevert(unittest.TestCase):
    def run_revert_step(self, missing, other_failure=False):
        workflow = (ROOT / '.github/workflows/deploy-check.yml').read_text()
        start = workflow.index('      - name: Revert the deploying commit')
        start = workflow.index('        run: |\n', start) + len('        run: |\n')
        end = workflow.index('      - name: Alert (daily check)', start)
        script = '\n'.join(line[10:] for line in workflow[start:end].splitlines())
        outcomes = {'oldlinks': 'failure', 'install': 'success', 'wait': 'success',
                    'scripts': 'success', 'journeys': 'failure' if other_failure else 'skipped'}
        def expand(match):
            expr = match.group(1).strip()
            if expr == 'steps.oldlinks.outputs.snapshot_missing':
                return 'true' if missing else ''
            if expr == 'github.sha':
                return 'a' * 40
            step = re.fullmatch(r'steps\.(\w+)\.outcome', expr)
            return outcomes.get(step.group(1), 'skipped') if step else ''
        script = re.sub(r'\$\{\{(.*?)\}\}', expand, script)
        # Execute the real workflow shell logic, with every external side effect replaced by echo.
        script = script.replace('python scripts/alert.py', 'echo ALERT')
        script = script.replace('bash scripts/revert_site.sh', 'echo REVERTED')
        script = script.replace('git log -1 --format=%s', 'echo Auto-revert')
        script = re.sub(r'(?m)(^|[;&|]\s*)git ', r'\1echo GIT ', script)
        env = dict(os.environ, CF_BLOCKED='', GITHUB_SERVER_URL='https://example.invalid',
                   GITHUB_REPOSITORY='public/site', GITHUB_RUN_ID='1')
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(['bash', '-e', '-c', script], cwd=directory, env=env, capture_output=True, text=True)

    def test_missing_snapshot_alerts_without_revert_or_push(self):
        result = self.run_revert_step(True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('automatic revert skipped: missing historical snapshot', result.stdout)
        self.assertIn('Historical snapshot missing - NOT reverted', result.stdout)
        self.assertNotIn('REVERTED', result.stdout)
        self.assertNotIn('GIT push', result.stdout)

    def test_real_link_failure_still_reverts(self):
        result = self.run_revert_step(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('REVERTED', result.stdout)
        self.assertIn('GIT push origin HEAD:main', result.stdout)

    def test_missing_snapshot_does_not_mask_an_independent_failure(self):
        result = self.run_revert_step(True, other_failure=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('REVERTED', result.stdout)


class PublicCheckoutCollection(unittest.TestCase):
    def test_private_replay_collects_and_skips_without_working_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'tests'
            tests.mkdir()
            module = tests / 'test_times_crosscheck_oct29_eighteen.py'
            shutil.copyfile(ROOT / 'tests' / module.name, module)
            (root / 'scripts').symlink_to(ROOT / 'scripts', target_is_directory=True)
            env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTEST_ADDOPTS='')
            for options, expected in ((['--collect-only'], '7 tests collected'), ([], '7 skipped')):
                result = subprocess.run(
                    [sys.executable, '-m', 'pytest', '-q', '-rs', *options, str(module)],
                    cwd=root, env=env, capture_output=True, text=True, timeout=60,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn(expected, output)
                self.assertNotIn('ERROR', output)
            self.assertIn('Private replay report is not available', output)
            for name in ('reports', 'logs', 'docs', 'email'):
                self.assertFalse((root / name).exists())
