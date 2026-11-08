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
            # -S proves this also works on refresh runners with no third-party test tools.
            script = """
import unittest
suite = unittest.defaultTestLoader.discover('tests', pattern='test_times_crosscheck_oct29_eighteen.py')
assert suite.countTestCases() == 7, suite.countTestCases()
print('7 tests collected')
result = unittest.TextTestRunner(verbosity=2).run(suite)
assert result.wasSuccessful(), 'Replay tests failed'
assert result.testsRun == 7, result.testsRun
assert len(result.skipped) == 7, result.skipped
assert all('Private replay report is not available' in reason for _, reason in result.skipped)
"""
            result = subprocess.run(
                [sys.executable, '-S', '-c', script],
                cwd=root, capture_output=True, text=True, timeout=60,
            )
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn('7 tests collected', output)
            self.assertIn('skipped=7', output)
            self.assertNotIn('ERROR', output)
            self.assertIn('Private replay report is not available', output)
            for name in ('reports', 'logs', 'docs', 'email'):
                self.assertFalse((root / name).exists())


class PublicCheckoutReports(unittest.TestCase):
    def writer(self, filename, function, root):
        # Exercise the actual writers without importing browser dependencies or running searches.
        import ast
        import json
        import time
        tree = ast.parse((ROOT / 'scripts' / filename).read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
        namespace = dict(ROOT=str(root), os=os, json=json, time=time)
        if filename == 'design_lock.py':
            # Its output block is inside run(); keep browser setup and layout checks out of this unit test.
            start = next(i for i, n in enumerate(node.body)
                         if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                         and ast.unparse(n.value.func) == 'os.makedirs')
            end = next(i for i, n in enumerate(node.body)
                       if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'base_c' for t in n.targets))
            node = ast.FunctionDef(name='write_report', args=ast.arguments(
                posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=node.body[start:end], decorator_list=[])
            namespace.update(base='local checkout', seen=1, counts={'fb': 1}, bad=['example failure'],
                             KNOWN=[], TILES=[], probe={'ok': True})
        module = ast.Module(body=[node], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), filename, 'exec'), namespace)
        return namespace[node.name]

    def test_reports_create_ignored_output_directories_in_empty_checkout(self):
        import json
        for name in ('journeys', 'design_lock', 'sense_check'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                writer = self.writer(name + '.py', 'run' if name == 'design_lock' else 'report', root)
                for _ in range(2):  # creating an existing output directory is safe too
                    if name == 'journeys':
                        self.assertEqual(writer({'example': {'pass': 0, 'fail': 1,
                                                            'failures': ['example failure']}}, None), 1)
                    elif name == 'sense_check':
                        writer(['example failure'], [{'ok': False}])
                    else:
                        writer()
                report = root / 'reports' / (name + '.md')
                log = root / 'logs' / (name + '.json')
                self.assertIn('example failure', report.read_text())
                payload = json.loads(log.read_text())
                if name == 'journeys':
                    self.assertEqual(payload['journeys']['example']['fail'], 1)
                elif name == 'sense_check':
                    self.assertEqual(payload['failed'], 1)
                else:
                    self.assertEqual(payload['bad'], ['example failure'])
                self.assertEqual({p.name for p in root.iterdir()}, {'reports', 'logs'})
                for path in (report, log):
                    ignored = subprocess.run(['git', 'check-ignore', '--', str(ROOT / path.relative_to(root))],
                                             cwd=ROOT, capture_output=True, text=True)
                    self.assertEqual(ignored.returncode, 0, ignored.stderr)


class PrivateWorkingFileReplay(unittest.TestCase):
    def replay_method(self, filename, method, root):
        # Extract only the method: no module imports, live files or production side effects.
        import ast
        import json
        tree = ast.parse((ROOT / 'tests' / filename).read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == method)
        module = ast.Module(body=[node], type_ignores=[])
        namespace = dict(ROOT=str(root), os=os, json=json, unittest=unittest)
        exec(compile(ast.fix_missing_locations(module), filename, 'exec'), namespace)
        return namespace[method]

    def test_missing_private_guard_reports_skip_without_creating_files(self):
        cases = (
            ('test_council_line_lock_29oct.py', 'test_undo_is_logged'),
            ('test_doorway_hours_lock.py', 'test_apply_log_marked_reverted'),
            ('test_times_review_29oct.py', 'test_logged_with_old_value_and_undo'),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, method in cases:
                replay = self.replay_method(filename, method, root)
                with self.subTest(filename=filename), self.assertRaisesRegex(unittest.SkipTest, 'Private working file'):
                    replay(self) if 'self' in replay.__code__.co_varnames else replay()
            self.assertEqual(list(root.iterdir()), [])

    def test_present_but_invalid_guard_report_is_not_skipped(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'reports').mkdir()
            (root / 'reports' / 'times_auto_applied.json').write_text('invalid json')
            replay = self.replay_method('test_doorway_hours_lock.py', 'test_apply_log_marked_reverted', root)
            with self.assertRaises(json.JSONDecodeError):
                replay(self)
