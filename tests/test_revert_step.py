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
        s = open(os.path.join(R, 'scripts', 'journeys.py')).read()
        self.assertIn("wait_until='load'", s); self.assertIn('J0 suite ran to the end', s)
