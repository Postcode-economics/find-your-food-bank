import json, os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import fb_page_check as F
def pg(t): return f'<html><head><meta property="og:title" content="{t}"></head></html>'
class T(unittest.TestCase):
    def test_baseline_is_the_verified_pages_minus_2_removed_25oct(self):
        P = json.load(open(os.path.join(R, "overrides", "facebook_pages.json")))
        pages = {k: v for k, v in P.items() if not k.startswith("_")}
        added = {"heston-farm"}  # Dean 28 Oct 08:15: Facebook group was only in the website field
        self.assertTrue(added <= set(pages)); self.assertEqual(len(pages), 51 + len(added)); self.assertTrue(all(v.get("page_title") and v.get("url") for v in pages.values()))
    def test_ok_changed_dead_unreachable(self):
        self.assertEqual(F.classify("Whitland Town Hall Community Food Bank", 200, pg("Whitland Town Hall Community Food Bank | Facebook"))[0], "ok")
        self.assertEqual(F.classify("Whitland Town Hall Community Food Bank", 200, pg("Cheap Watches Online"))[0], "changed")
        self.assertEqual(F.classify("X Food Bank", 404, "")[0], "dead")
        self.assertEqual(F.classify("X Food Bank", 429, "")[0], "unreachable")
        self.assertEqual(F.classify("X Food Bank", 200, "<title>Facebook</title> This content isn't available right now")[0], "dead")
    def test_flag_never_removes(self):
        P = {"a": {"url": "u", "page_title": "A Food Bank"}}; before = json.dumps(P)
        res = F.run(P, fetcher=lambda u: (404, ""), delay=0)
        self.assertEqual(res["a"]["status"], "dead"); self.assertEqual(json.dumps(P), before)
        self.assertIn("dead", F.report(res, "d")); self.assertIn("Nothing was removed", F.report(res, "d"))
if __name__ == "__main__": unittest.main()
