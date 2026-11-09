"""Plan 1.5: refresh fetchers use one HelpMapBot agent so councils can allow-list us.

Locks common.get and discover's first-try + retry agents to the same HelpMapBot string (helpmap.uk).
Does not loosen any guard: identification is tighter, not weaker. Facebook, browser-check and
rest-centre browser-like agents are unchanged (different jobs).
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common
import discover as D


class HelpMapBotUA(unittest.TestCase):
    def test_common_and_discover_share_helpmapbot(self):
        self.assertIn("HelpMapBot/1.0", common.HELPMAP_BOT)
        self.assertIn("https://helpmap.uk/", common.HELPMAP_BOT)
        self.assertEqual(common.UA["User-Agent"], common.HELPMAP_BOT)
        self.assertEqual(D.UA["User-Agent"], common.HELPMAP_BOT)
        self.assertEqual(D.POLITE_UA["User-Agent"], common.HELPMAP_BOT)
        self.assertEqual(D.HELPMAP_BOT, common.HELPMAP_BOT)

    def test_no_old_github_io_agent(self):
        self.assertNotIn("postcode-economics.github.io", common.UA["User-Agent"])
        self.assertNotIn("FindYourFoodBank refresh", D.UA["User-Agent"])


if __name__ == "__main__":
    unittest.main()
