import json, os, re, shutil, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(R, "scripts"))

SWINDON = open(os.path.join(os.path.dirname(__file__), "fixtures", "swindon_swep_comment.html"), encoding="utf-8").read()

FAKE_GH = """#!/bin/bash
echo "$*" >> "$GH_CALLS"
case "$1 $2" in
  "issue list") [ -n "$GH_LIST" ] && printf '%s' "$GH_LIST" || echo '[]';;
  "label create") ;;
esac
exit 0
"""


class VisibleText(unittest.TestCase):
    def test_swindon_comment_not_active(self):
        import swep
        from page_visible import html_to_visible_text
        t = html_to_visible_text(SWINDON)
        self.assertNotIn("currently active in Swindon", t.replace("not currently active", ""))
        st, _ = swep.classify(t, "2026-10-30")
        self.assertEqual(st, "not active")


class EmergencySwitchOn(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.root = self.d
        os.makedirs(os.path.join(self.d, "overrides"))
        os.makedirs(os.path.join(self.d, "logs"))
        os.makedirs(os.path.join(self.d, "reports"))
        os.makedirs(os.path.join(self.d, "bin"))
        gh = os.path.join(self.d, "bin", "gh")
        open(gh, "w").write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.calls = os.path.join(self.d, "calls")
        self.env = dict(
            os.environ,
            PATH=os.path.join(self.d, "bin") + os.pathsep + os.environ["PATH"],
            GH_CALLS=self.calls,
            GITHUB_REPOSITORY="Postcode-economics/find-your-food-bank",
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_RUN_ID="999",
        )
        self._old_env = os.environ.copy()
        os.environ.update(self.env)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._old_env)
        shutil.rmtree(self.d, ignore_errors=True)

    def gh_calls(self):
        return open(self.calls).read().splitlines() if os.path.exists(self.calls) else []

    def write_prev(self, status="unknown", council="Test Council", url="https://x.gov.uk/swep"):
        prev = {
            "run": "2026-10-29",
            "sources": 1,
            "active": [],
            "changes": [],
            "pages": [{"council": council, "url": url, "http": 200, "status": status, "quote": "", "rest_centre": None}],
        }
        json.dump(prev, open(os.path.join(self.d, "logs", "swep_status.json"), "w"))
        return prev

    def run_swep(self, html, prev_status="unknown"):
        import swep as W
        self.write_prev(prev_status)
        json.dump([{"council": "Test Council", "url": "https://x.gov.uk/swep"}], open(os.path.join(self.d, "overrides", "swep_sources.json"), "w"))
        cwd = os.getcwd()
        old_env = os.environ.copy()
        os.environ.update(self.env)
        try:
            os.chdir(self.d)
            f = lambda u: {"http": 200, "html": html}
            return W.run(fetcher=f, run_day="2026-10-30")
        finally:
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def test_off_to_on_one_issue_and_status_and_pending(self):
        r = self.run_swep("<p>SWEP is now active tonight in Testville.</p>", prev_status="unknown")
        self.assertEqual(r["active"], ["Test Council"])
        self.assertEqual(len(r["changes"]), 1)
        st = json.load(open(os.path.join(self.d, "logs", "swep_status.json")))
        self.assertIn("Test Council", st["active"])
        pd = open(os.path.join(self.d, "reports", "pending_dean.md")).read()
        self.assertIn("emergency switch-on", pd)
        self.assertIn("Test Council", pd)
        creates = [c for c in self.gh_calls() if c.startswith("issue create --title Emergency shelter ON:")]
        self.assertEqual(len(creates), 1)

    def test_staying_on_no_second_issue(self):
        self.run_swep("<p>SWEP is now active tonight.</p>", prev_status="unknown")
        self.env["GH_LIST"] = '[{"number": 1, "title": "Emergency shelter ON: Test Council - SWEP"}]'
        n0 = len([c for c in self.gh_calls() if "issue create" in c])
        self.run_swep("<p>SWEP is now active tonight still.</p>", prev_status="active")
        n1 = len([c for c in self.gh_calls() if "issue create" in c])
        self.assertEqual(n0, n1)

    def test_on_to_off_closes(self):
        self.run_swep("<p>SWEP is now active tonight.</p>", prev_status="unknown")
        old = os.environ.copy()
        os.environ.update(self.env)
        os.environ["GH_LIST"] = '[{"number": 5, "title": "Emergency shelter ON: Test Council - SWEP"}]'
        try:
            self.run_swep("<p>SWEP has been stood down.</p>", prev_status="active")
        finally:
            os.environ.clear()
            os.environ.update(old)
        self.assertTrue(any(c.startswith("issue close 5") for c in self.gh_calls()))
        pd = open(os.path.join(self.d, "reports", "pending_dean.md")).read()
        self.assertNotIn("**Test Council** — SWEP", pd)

    def test_swindon_fixture_not_on(self):
        import swep as W
        self.write_prev("active")  # was wrongly active
        json.dump([{"council": "Swindon Borough Council", "url": "https://swindon.example/swep"}], open(os.path.join(self.d, "overrides", "swep_sources.json"), "w"))
        cwd = os.getcwd()
        try:
            os.chdir(self.d)
            r = W.run(fetcher=lambda u: {"http": 200, "html": SWINDON}, run_day="2026-10-30")
            self.assertNotIn("Swindon Borough Council", r["active"])
        finally:
            os.chdir(cwd)

    def test_flood_rest_centre_counts_as_on(self):
        import emergency_switch_on as eso
        text = "Due to flooding, the rest centre at Riverside Hall PO21 1XY has been opened for residents."
        act = eso.rest_centre_activation(text, "Arun District Council", "https://example.gov.uk/emergency")
        self.assertIsNotNone(act)
        self.assertEqual(act["kind"], "rest_centre")
        self.assertIn("opened", act["quote"].lower())


if __name__ == "__main__":
    unittest.main()
