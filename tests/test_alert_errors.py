"""Fault scan 28 Oct (10-11): alerts must not fail silently.
alert.py exits non-zero when gh fails; the digest step fails when an alert can't be raised; the food bank and
warm spaces refreshes never share an alert key; deploy-check never tests the old live build 'anyway'."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WF = os.path.join(R, ".github", "workflows")
ALERT = os.path.join(R, "scripts", "alert.py")
rd = lambda *p: open(os.path.join(*p), encoding="utf-8").read()

FAKE_GH = """#!/bin/bash
echo "$*" >> "$GH_CALLS"
case "$1 $2" in
  "issue list") [ -n "$GH_LIST" ] && printf '%s' "$GH_LIST" || echo '[]';;
esac
[ -n "$GH_FAIL_ON" ] && [[ "$1 $2" == "$GH_FAIL_ON" ]] && { echo "HTTP 403: Resource not accessible by integration" >&2; exit 1; }
exit 0
"""


class AlertPy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "bin"))
        gh = os.path.join(self.d, "bin", "gh")
        open(gh, "w").write(FAKE_GH); os.chmod(gh, 0o755)
        self.calls = os.path.join(self.d, "calls")
        self.env = dict(os.environ, PATH=os.path.join(self.d, "bin") + os.pathsep + os.environ["PATH"], GH_CALLS=self.calls)
        self.env.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_alert(self, *args, **env):
        return subprocess.run([sys.executable, ALERT, *args], env=dict(self.env, **env), capture_output=True, text=True)

    def gh_calls(self):
        return open(self.calls).read().splitlines() if os.path.exists(self.calls) else []

    def test_open_and_resolve_succeed(self):
        r = self.run_alert("open", "k1", "Title", "Body")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(c.startswith("issue create --title [k1] Title") for c in self.gh_calls()), self.gh_calls())
        r = self.run_alert("resolve", "k1", GH_LIST='[{"number": 7, "title": "[k1] Title"}]')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(any(c.startswith("issue close 7") for c in self.gh_calls()), self.gh_calls())

    def test_failed_create_fails_the_step(self):
        r = self.run_alert("open", "k1", "Title", "Body", GH_FAIL_ON="issue create")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT raised", r.stdout)
        self.assertIn("::error::alert.py failed", r.stderr)

    def test_failed_close_fails_the_step(self):
        r = self.run_alert("resolve", "k1", GH_LIST='[{"number": 7, "title": "[k1] Title"}]', GH_FAIL_ON="issue close")
        self.assertNotEqual(r.returncode, 0)

    def test_failed_lookup_never_opens_a_duplicate(self):
        r = self.run_alert("open", "k1", "Title", "Body", GH_FAIL_ON="issue list")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(any(c.startswith("issue create") for c in self.gh_calls()), self.gh_calls())
        r = self.run_alert("open", "k1", "Title", "Body", GH_LIST="not json")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(any(c.startswith("issue create") for c in self.gh_calls()), self.gh_calls())

    def test_gh_missing_fails(self):
        empty = os.path.join(self.d, "empty"); os.makedirs(empty)
        env = dict(self.env, PATH=empty)
        r = subprocess.run([sys.executable, ALERT, "resolve", "k1"], env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_unknown_command_fails(self):
        self.assertNotEqual(self.run_alert("opne", "k1").returncode, 0)


class Digest(unittest.TestCase):
    def test_alert_failure_fails_and_keeps_state(self):
        sys.path.insert(0, os.path.join(R, "scripts"))
        import digest as D
        d = tempfile.mkdtemp()
        saved = (D.P, D.ST, D.MD, os.environ.get("GITHUB_ACTIONS"))
        try:
            for sub in ("logs", "reports", "scripts"):
                os.makedirs(os.path.join(d, sub))
            open(os.path.join(d, "scripts", "alert.py"), "w").write("import sys; sys.exit(1)\n")
            json.dump({"a": [{"id": "a", "name": "A FB", "change": "removed", "label": "real closure (own site says closed)",
                              "when": "2026-10-28T05:00:00+00:00"}]}, open(os.path.join(d, "logs", "entry_history.json"), "w"))
            st = os.path.join(d, "logs", "digest_state.json")
            json.dump({"last_run": "2026-10-27T05:00:00+00:00"}, open(st, "w"))
            D.P = lambda *a: os.path.join(d, *a); D.ST = st; D.MD = os.path.join(d, "reports", "morning_digest.md")
            os.environ["GITHUB_ACTIONS"] = "true"
            with self.assertRaises(RuntimeError):
                D.main()
            self.assertEqual(json.load(open(st))["last_run"], "2026-10-27T05:00:00+00:00")
        finally:
            D.P, D.ST, D.MD, ga = saved
            if ga is None: os.environ.pop("GITHUB_ACTIONS", None)
            else: os.environ["GITHUB_ACTIONS"] = ga
            shutil.rmtree(d, ignore_errors=True)

    def test_main_exits_non_zero_on_error(self):
        src = rd(R, "scripts", "digest.py")
        tail = src[src.index('if __name__ == "__main__":'):]
        self.assertIn("sys.exit(1)", tail)
        self.assertNotIn("not fatal", tail)


def step(text, name):
    i = text.index("- name: " + name)
    j = text.find("\n      - ", i + 1)
    return text[i:j if j > 0 else len(text)]


class Workflows(unittest.TestCase):
    def test_digest_step_is_not_continue_on_error(self):
        s = step(rd(WF, "refresh.yml"), "Alerts + morning digest")
        self.assertIn("python scripts/digest.py", s)
        self.assertNotIn("continue-on-error: true", s)

    def test_refreshes_never_share_an_alert_key(self):
        keys = lambda n: set(re.findall(r"alert\.py (?:open|resolve) ([\w-]+)", rd(WF, n)))
        fb, ws = keys("refresh.yml"), keys("refresh-warmspaces.yml")
        self.assertIn("seo-foodbanks", fb)
        self.assertIn("seo-warmspaces", ws)
        self.assertEqual(fb & ws, set())

    def test_deploy_wait_never_tests_anyway(self):
        d = rd(WF, "deploy-check.yml")
        self.assertNotIn("testing anyway", d)
        live = d[d.index("id: wait"):d.index("id: oldlinks")]
        self.assertRegex(live, r"this commit is not live.*\n\s*exit 1")
        tile = d[d.index("tile-fallback:"):]
        wait = tile[tile.index("Wait for the deploy"):tile.index("id: fallback")]
        self.assertIn("exit 1", wait)
        self.assertIn("SUPERSEDED=1", wait)

    def test_not_live_is_alerted_never_reverted(self):
        d = rd(WF, "deploy-check.yml")
        blk = d[d.index("Revert the deploying commit"):d.index("- name: Alert (daily check)")]
        nl = blk.index('if [ "$failed" = "deploy-wait" ]')
        self.assertLess(nl, blk.index("revert_site.sh"))
        self.assertIn("exit 1", blk[nl:blk.index("fi", nl)])


if __name__ == "__main__":
    unittest.main()
