"""A failed fetch method falls through to the one that works, and that method is tried first next time."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import learning, full_check as F
from test_learning_guards import assert_schedule_and_guards

class Heal(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("learning.method_order(LS, u, avail)", fc)
        self.assertIn("learning.note_heal(LS, u", fc)
    def test_failed_method_falls_through_and_is_remembered(self):
        s = learning.load(os.devnull); seen = []
        def attempt(m):
            seen.append(m); return (m == "render", {"via": m} if m == "render" else None)
        r = learning.heal(s, "site", "2026-10-26", ["plain", "render"], attempt)
        self.assertEqual(r["tried"], ["plain", "render"]); self.assertTrue(r["healed"]); self.assertEqual(r["result"], {"via": "render"})
        self.assertEqual(s["keys"]["site"]["healed_from"], "plain"); self.assertEqual(s["keys"]["site"]["healed_to"], "render")
        learning.record(s, "site", "2026-10-26", True, method="render")
        seen[:] = []
        r2 = learning.heal(s, "site", "2026-10-27", ["plain", "render"], lambda m: (m == "render", {"ok": 1}))
        self.assertEqual(r2["tried"], ["render"])  # the method that worked is now first, and the failed one is not retried
        bad = learning.heal(s, "gone", "2026-10-27", ["plain", "render"], lambda m: (False, None))
        self.assertFalse(bad["ok"]); self.assertIsNone(bad["result"]); self.assertIsNone(bad["method"])
    def test_check_site_uses_the_given_order(self):
        calls = []
        def fake(url):
            calls.append(url)
            if url.startswith("https://"): return {"ok": True, "http": 200, "final_url": url, "html": "<html><title>ok</title></html>"}
            return {"ok": False, "http": 500, "error": "HTTP 500"}
        old = F.fetch; F.fetch = fake
        try:
            first = F.check_site("http://example.test/page", ["plain", "https"])
            self.assertEqual(first["methods_tried"], ["plain", "https"]); self.assertEqual(first["method"], "https"); self.assertTrue(first["ok"])
            calls[:] = []
            second = F.check_site("http://example.test/page", ["https", "plain"])
            self.assertEqual(calls, ["https://example.test/page"]); self.assertEqual(second["method"], "https")
        finally:
            F.fetch = old

if __name__ == "__main__": unittest.main()
