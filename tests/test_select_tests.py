"""Targeted-test picker (scripts/select_tests.py) and its CI wiring (Dean 2 Nov 2026)."""
import os, re, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import select_tests as st  # noqa: E402


class Picker(unittest.TestCase):
    def all_(self, *files):
        sel, why = st.main(list(files))
        self.assertIsNone(sel, '%s should run the full suite, got %r (%s)' % (files, sel, why))

    def test_site_data_and_shared_files_run_everything(self):
        for f in ['index.html', 'layers.js', 'sw.js', 'style.css', 'data.js', 'data.full.js',
                  'shelters.js', 'warmspaces.js', 'assets/x.js', 'overrides/warmspaces_manual.json',
                  'scripts/common.py', 'scripts/select_tests.py', '.github/workflows/tests.yml',
                  'tests/site_ready.py', 'tests/conftest.py']:
            self.all_(f)

    def test_one_full_suite_file_wins_over_a_mapped_one(self):
        self.all_('tests/test_workflow_scripts.py', 'sw.js')

    def test_empty_huge_and_unmapped_run_everything(self):
        self.all_()
        self.all_(*['f%d.md' % i for i in range(300)])
        self.all_('no_test_names_' + 'this_file_' + 'zz9.txt')

    def test_changed_test_file_runs_itself(self):
        sel, _ = st.main(['tests/test_workflow_scripts.py'])
        self.assertEqual(sel, ['tests/test_workflow_scripts.py'])

    def test_cli_prints_ALL(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'select_tests.py'), 'sw.js'],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'ALL')


class Workflow(unittest.TestCase):
    def setUp(self):
        self.y = open(os.path.join(ROOT, '.github', 'workflows', 'tests.yml'), encoding='utf-8').read()

    def test_runs_mains_picker_not_the_prs(self):
        self.assertIn('git show origin/main:scripts/select_tests.py > /tmp/select_tests.py', self.y)
        self.assertIn('python /tmp/select_tests.py', self.y)
        self.assertNotRegex(self.y, r'python\s+scripts/select_tests\.py')

    def test_no_renames_and_full_suite_fallbacks(self):
        self.assertIn('git diff --no-renames --name-only', self.y)
        self.assertIn('no picker on main: full suite', self.y)
        self.assertIn('|| sel=ALL', self.y)
        for ev in ('refs/heads/main', 'schedule', 'workflow_dispatch'):
            self.assertIn(ev, self.y)


if __name__ == '__main__':
    unittest.main()
