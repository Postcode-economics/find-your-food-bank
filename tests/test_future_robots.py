"""A robots.txt disallow skips the fetch. Hours are not guessed and the place is not removed."""
import os, sys, unittest
R = os.path.join(os.path.dirname(__file__), ".."); sys.path.insert(0, os.path.join(R, "scripts"))
import robots_check, full_check as F, learning
from test_learning_guards import assert_schedule_and_guards

class Robots(unittest.TestCase):
    def test_schedule_and_floor_unchanged(self):
        assert_schedule_and_guards()
        self.assertEqual(learning.FLOOR_DAYS, 7)
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("not fetched, robots", fc)
        self.assertIn("5 3,11,19 * * *", open(os.path.join(R, ".github", "workflows", "sweep-daily.yml"), encoding="utf-8").read())
    def test_disallow_rules(self):
        self.assertFalse(robots_check.blocked("", "/page"))
        self.assertFalse(robots_check.blocked("User-agent: *\nDisallow:\n", "/page"))
        self.assertTrue(robots_check.blocked("User-agent: *\nDisallow: /\n", "/page"))
        self.assertTrue(robots_check.blocked("User-agent: *\nDisallow: /private\n", "/private/hours"))
        self.assertFalse(robots_check.blocked("User-agent: *\nDisallow: /private\n", "/public"))
        self.assertFalse(robots_check.blocked("User-agent: other\nDisallow: /\n", "/page"))
    def test_blocked_page_is_not_read(self):
        F._robots_cache.clear()
        def fake(url):
            if url.endswith("/robots.txt"):
                return {"ok": True, "http": 200, "final_url": url, "html": "User-agent: *\nDisallow: /\n"}
            return {"ok": True, "http": 200, "final_url": url, "html": "<p>Monday 9am - 5pm</p><a href='tel:01000000000'>call</a>"}
        old = F.fetch; F.fetch = fake
        try:
            r = F.check_site("https://blocked.test/hours")
        finally:
            F.fetch = old; F._robots_cache.clear()
        self.assertTrue(r["robots"])
        self.assertEqual(r["error"], "not fetched, robots")
        self.assertEqual(r["hours_hash"], "")
        self.assertEqual(r["phones"], [])
        self.assertEqual(r["methods_tried"], [])

if __name__ == "__main__":
    unittest.main()
