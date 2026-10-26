"""The tests workflow must not fill the 20-job hosted-runner cap.

On 25 Oct 2026 the cap was full of browser-tests, old-links and design-lock jobs
for commits that do not touch the site. Main's tests, the deploy check, Pages
and the watchdog then sat in the queue with no runner.
"""
import os, unittest
R = os.path.join(os.path.dirname(__file__), '..')
Y = open(os.path.join(R, '.github', 'workflows', 'tests.yml'), encoding='utf-8').read()

class Cap(unittest.TestCase):
    def test_one_run_per_branch_and_a_newer_push_cancels_the_older(self):
        self.assertIn('group: tests-${{ github.head_ref || github.ref_name }}', Y)
        self.assertIn('cancel-in-progress: true', Y)

    def test_long_jobs_wait_to_be_asked_for(self):
        for job, out in (('old-links', 'oldlinks'), ('browser-tests', 'browser'),
                         ('design-lock', 'design'), ('journeys', 'journeys')):
            self.assertIn("needs.changes.outputs.%s == '1'" % out, Y, job)
        # the plain pytest job always runs; it is not behind that gate
        test_job = Y.split('\n  test:\n', 1)[1].split('\n  old-links:', 1)[0]
        self.assertNotIn('needs:', test_job)
        self.assertIn('python scripts/old_links.py\n', Y)

    def test_a_learning_script_does_not_count_as_the_site(self):
        # the case list in the workflow: site html/css/js queues the long jobs,
        # a learning script does not, a browser test file does
        self.assertIn('*.html|*.css|*.js)', Y)
        self.assertIn('tests/*.py)', Y)
        self.assertIn('grep -q playwright', Y)
        self.assertNotIn('scripts/learning.py)', Y)
