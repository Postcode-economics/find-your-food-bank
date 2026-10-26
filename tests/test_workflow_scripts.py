"""An auto-revert puts the site files back and leaves the workflow in place. A workflow that then
calls a script which is no longer in the tree must fail with that reason, not with a missing-file
traceback from a later step."""
import os, re, subprocess, sys, tempfile, textwrap, unittest
R = os.path.join(os.path.dirname(__file__), '..')
SENTENCE = ('auto-revert restores site files and leaves the workflow in place, '
            'so a workflow calls a script that is not in this tree')


def _guard_source():
    yml = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml'), encoding='utf-8').read()
    m = re.search(r"python - <<'PY'\n(.*?)\n[ \t]*PY\n", yml, re.S)
    if not m:
        raise AssertionError('deploy-check.yml has no workflow-script guard')
    return textwrap.dedent(m.group(1))


def _run_guard(cwd):
    return subprocess.run([sys.executable, '-c', _guard_source()], cwd=cwd, capture_output=True, text=True)


class WorkflowScripts(unittest.TestCase):
    def test_a_missing_script_named_by_a_workflow_fails_clearly(self):
        yml = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml'), encoding='utf-8').read()
        self.assertIn(SENTENCE, yml)
        self.assertEqual(yml.count('steps.scripts.outcome'), 2)  # push revert and the daily alert
        self.assertIn('id: scripts', yml)
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, '.github', 'workflows'))
            open(os.path.join(d, '.github', 'workflows', 'deploy-check.yml'), 'w').write(
                'run: python scripts/dark_default.py https://helpmap.uk\n')
            r = _run_guard(d)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(SENTENCE, r.stdout + r.stderr)
            self.assertIn('scripts/dark_default.py', r.stdout + r.stderr)
        finally:
            import shutil
            shutil.rmtree(d)

    def test_this_tree_has_every_script_a_workflow_calls(self):
        r = _run_guard(R)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(SENTENCE, r.stdout + r.stderr)
