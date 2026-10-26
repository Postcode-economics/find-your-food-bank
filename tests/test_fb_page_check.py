import json, os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import fb_page_check as F
def pg(t): return f'<html><head><meta property="og:title" content="{t}"></head></html>'
class T(unittest.TestCase):
    def test_baseline_is_the_verified_pages_minus_2_removed_25oct(self):
        P = json.load(open(os.path.join(R, "overrides", "facebook_pages.json")))
        pages = {k: v for k, v in P.items() if not k.startswith("_")}
        self.assertEqual(len(pages), 51); self.assertTrue(all(v.get("page_title") and v.get("url") for v in pages.values()))
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
    def test_pause_between_pages_is_random_45_to_120_and_serial(self):
        import unittest.mock as mock
        order = []
        bounds = iter([45, 120])
        def fetcher(u):
            order.append("fetch")
            return 200, pg("T Food Bank")
        def randint(a, b):
            self.assertEqual((a, b), (F.GAP_MIN, F.GAP_MAX))
            return next(bounds)
        pages = {"a": {"url": "https://example.test/a", "page_title": "T Food Bank"},
                 "b": {"url": "https://example.test/b", "page_title": "T Food Bank"},
                 "c": {"url": "https://example.test/c", "page_title": "T Food Bank"},
                 "_note": {"url": "skip", "page_title": "skip"}}
        with mock.patch("fb_page_check.random.randint", side_effect=randint), \
             mock.patch("fb_page_check.time.sleep", side_effect=lambda n: order.append(("sleep", n))):
            res = F.run(pages, fetcher=fetcher)
        # One page at a time: the next fetch starts only after the previous sleep returns.
        self.assertEqual(order, ["fetch", ("sleep", 45), "fetch", ("sleep", 120), "fetch"])
        self.assertEqual((F.GAP_MIN, F.GAP_MAX), (45, 120))
        self.assertEqual(set(res), {"a", "b", "c"})
        self.assertIsNone(F.run.__defaults__[1])  # delay defaults to the random gap, not a fixed pause
if __name__ == "__main__": unittest.main()
