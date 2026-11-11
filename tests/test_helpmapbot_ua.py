"""Plan 1.5 (as narrowed by the #499 practice evidence, 11 Nov 2026).

HelpMapBot is the one identified agent on discover's polite 403/429 retry, shared with common.HELPMAP_BOT.
First tries keep their earlier agents: with HelpMapBot on the first try, ~60 more food bank own sites were
unreachable (153/154 vs 86-96) and the shelters build read 331 listings instead of 364-365.
No guard loosened: retry codes, tries, backoff and timeouts are unchanged.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common
import discover as D


class HelpMapBotUA(unittest.TestCase):
    def test_retry_uses_shared_helpmapbot(self):
        self.assertIn("HelpMapBot/1.0", common.HELPMAP_BOT)
        self.assertIn("https://helpmap.uk/", common.HELPMAP_BOT)
        self.assertEqual(D.HELPMAP_BOT, common.HELPMAP_BOT)
        self.assertEqual(D.POLITE_UA["User-Agent"], common.HELPMAP_BOT)

    def test_discover_first_try_is_browser_like_not_helpmapbot(self):
        self.assertEqual(D.UA["User-Agent"], "Mozilla/5.0 (FindYourFoodBank refresh; own-site check)")
        self.assertNotIn("HelpMapBot", D.UA["User-Agent"])
        self.assertNotEqual(D.UA["User-Agent"], D.POLITE_UA["User-Agent"])

    def test_common_get_first_try_unchanged(self):
        self.assertEqual(common.UA["User-Agent"],
                         "postcode-economics-map/1.0 (+https://postcode-economics.github.io/find-your-food-bank/)")


if __name__ == "__main__":
    unittest.main()
