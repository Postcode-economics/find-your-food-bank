"""25 Oct: the auto-revert step must fail loudly (set -e, no && chain) and clean the tree before pulling."""
import os, unittest
R = os.path.join(os.path.dirname(__file__), '..')
class T(unittest.TestCase):
    def test_revert_step(self):
        y = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml')).read()
        i = y.index('Revert the deploying commit'); blk = y[i:y.index('- name:', i + 10)]
        self.assertIn('set -euo pipefail', blk); self.assertIn('git reset -q --hard', blk)
        self.assertNotIn('main && bash', blk); self.assertIn('Auto-revert', blk)
    def test_journeys_no_networkidle_load(self):
        # PR 127 replaced the blanket wait_until='load' retry (it also retried a bot page) with
        # check_browser.open_page: domcontentloaded, then the search box, list and map pane.
        s = open(os.path.join(R, 'scripts', 'journeys.py')).read()
        self.assertNotIn("wait_until='networkidle'", s)
        self.assertNotIn('for attempt in (1, 2)', s)
        self.assertIn('open_page', s)
        self.assertIn('J0 suite ran to the end', s)


class SupersededAndV88(__import__('unittest').TestCase):
    """25 Oct 20:23: a superseded deploy-check run must stand down (no checks, no revert); v88 is never auto-reverted."""
    def test_guards(self):
        import os
        s = open(os.path.join(os.path.dirname(__file__), '..', '.github', 'workflows', 'deploy-check.yml')).read()
        self.assertIn('SUPERSEDED=1', s); self.assertIn("env.SUPERSEDED != '1'", s); self.assertIn('ad54c561*', s)
