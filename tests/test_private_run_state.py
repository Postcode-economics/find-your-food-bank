"""Private run state (rule 97): logs/ and reports/ persist between runs only through the private vault repo.

Locks in: each refresh and the deep sweep restores saved state right after checkout and saves it only on main,
using the HELPMAP_STATE_KEY secret; nothing internal is uploaded as an artifact of this public repo; the script
never prints file contents; and a round trip through a local stand-in repo restores exactly what was saved.
Grok Bot 2 on #491: (a) no restored state -> times auto-apply off for that run; (b) one private folder per layer,
undo logs merged, a refused push retried; (c) restored files are never staged for the public repo; (d) the sweep has
no practice mode (rule 94), so its sync is covered here by unit tests with the 'sweep' label."""
import os, shutil, subprocess, sys, tempfile, unittest
try:
    import yaml
except ImportError:  # same as the other workflow guard tests: the refresh runners start without pyyaml
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(ROOT, "scripts", "private_state.sh")
WORKFLOWS = {"refresh.yml": "foodbanks", "refresh-shelters.yml": "shelters",
             "refresh-warmspaces.yml": "warmspaces", "sweep-daily.yml": "sweep"}


def steps(name):
    wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8"))
    return next(iter(wf["jobs"].values()))["steps"]


class Workflows(unittest.TestCase):
    def test_restore_right_after_checkout(self):
        for name in WORKFLOWS:
            st = steps(name)
            i = next(n for n, s in enumerate(st) if str(s.get("uses", "")).startswith("actions/checkout"))
            r = st[i + 1]
            self.assertEqual(r.get("run", "").strip(), "bash scripts/private_state.sh restore", name)
            self.assertEqual(r["env"]["HELPMAP_STATE_KEY"], "${{ secrets.HELPMAP_STATE_KEY }}", name)

    def test_save_on_main_only_after_commit(self):
        for name, label in WORKFLOWS.items():
            st = steps(name)
            com = next(n for n, s in enumerate(st) if str(s.get("name", "")).startswith("Commit"))
            sv = [n for n, s in enumerate(st) if "private_state.sh save" in s.get("run", "")]
            self.assertEqual(len(sv), 1, name)
            s = st[sv[0]]
            self.assertGreater(sv[0], com, name)
            self.assertIn("refs/heads/main", s.get("if", ""), name)
            self.assertIn("success()", s.get("if", ""), name)
            self.assertEqual(s["run"].strip(), "bash scripts/private_state.sh save " + label, name)

    def test_state_steps_can_never_fail_or_hang_a_run(self):
        for name in WORKFLOWS:
            for s in steps(name):
                if "private_state.sh" in s.get("run", ""):
                    self.assertIs(s.get("continue-on-error"), True, name)
                    self.assertLessEqual(int(s.get("timeout-minutes", 999)), 5, name)

    def test_secret_only_in_state_steps(self):
        for name in WORKFLOWS:
            for s in steps(name):
                if "HELPMAP_STATE_KEY" in str(s.get("env", "")):
                    self.assertIn("private_state.sh", s.get("run", ""), name)

    def test_no_internal_artifacts(self):
        for f in WORKFLOWS:
            t = open(os.path.join(ROOT, ".github", "workflows", f), encoding="utf-8").read()
            for s in yaml.safe_load(t)["jobs"].values():
                for x in s.get("steps", []):
                    if "upload-artifact" in str(x.get("uses", "")):
                        path = str((x.get("with") or {}).get("path", ""))
                        self.assertNotRegex(path, r"(^|\s|/)(logs|reports)(/|\s|$)", f)

    def test_script_never_prints_contents(self):
        t = open(SCRIPT, encoding="utf-8").read()
        for bad in ("cat ", "set -x", "head ", "tail ", "upload-artifact", "find-your-food-bank"):
            self.assertNotIn(bad, t)
        self.assertIn("helpmap-research-backup", t)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.remote = os.path.join(self.d, "private.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.remote], check=True)
        seed = os.path.join(self.d, "seed")
        subprocess.run(["git", "clone", "-q", self.remote, seed], check=True)
        open(os.path.join(seed, "README.md"), "w").write("vault\n")
        g = ["git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["commit", "-qm", "seed"], check=True)
        subprocess.run(g + ["push", "-q", "origin", "HEAD:main"], check=True)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_in(self, cwd, *args, key="test-key", ref="refs/heads/main"):
        self.genv = os.path.join(self.d, "github_env-" + os.path.basename(cwd))
        open(self.genv, "w").close()
        env = dict(os.environ, PRIVATE_STATE_REPO="file://" + self.remote, HELPMAP_STATE_KEY=key, GITHUB_REF=ref,
                   PRIVATE_STATE_RETRY_WAIT="0", GITHUB_ENV=self.genv,
                   PRIVATE_STATE_WORK=os.path.join(self.d, "work-" + os.path.basename(cwd)))
        return subprocess.run(["bash", SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True)

    def restored_flag(self):
        return "HELPMAP_STATE_RESTORED=1" in open(self.genv).read()

    def vault_files(self):
        out = subprocess.run(["git", "--git-dir", self.remote, "ls-tree", "-r", "--name-only", "main"],
                             capture_output=True, text=True, check=True).stdout.split()
        return [f for f in out if f.startswith("site-run-state/")]

    def write(self, root, rel, text):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        open(os.path.join(root, rel), "w").write(text)

    def checkout(self, name):
        p = os.path.join(self.d, name); os.makedirs(p); return p

    def test_save_then_restore(self):
        a = self.checkout("run1")
        self.assertIn("no saved state", self.run_in(a, "restore").stdout)
        os.makedirs(os.path.join(a, "logs")); os.makedirs(os.path.join(a, "reports"))
        open(os.path.join(a, "logs", "times_crosscheck_seen.json"), "w").write('{"x": 1}')
        open(os.path.join(a, "reports", "learning_state.json"), "w").write('{"keys": {}}')
        r = self.run_in(a, "save", "warmspaces")
        self.assertIn("saved 2", r.stdout, r.stdout + r.stderr)
        self.assertNotIn('{"x": 1}', r.stdout + r.stderr)
        b = self.checkout("run2")
        self.assertIn("restored 2", self.run_in(b, "restore").stdout)
        self.assertEqual(open(os.path.join(b, "logs", "times_crosscheck_seen.json")).read(), '{"x": 1}')
        self.assertIn("no changed state files", self.run_in(b, "save", "sweep").stdout)

    def test_no_key_does_nothing(self):
        a = self.checkout("nokey")
        r = self.run_in(a, "restore", key="")
        self.assertEqual(r.returncode, 0); self.assertIn("no HELPMAP_STATE_KEY", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(a, "logs")))

    def test_not_main_saves_nothing(self):
        a = self.checkout("branch")
        self.run_in(a, "restore")
        os.makedirs(os.path.join(a, "logs")); open(os.path.join(a, "logs", "x.json"), "w").write("{}")
        self.assertIn("not main", self.run_in(a, "save", "shelters", ref="refs/heads/practice").stdout)
        b = self.checkout("after")
        self.assertIn("no saved state", self.run_in(b, "restore").stdout)

    def test_checkout_files_win_on_restore(self):
        a = self.checkout("w1"); self.run_in(a, "restore")
        os.makedirs(os.path.join(a, "logs")); open(os.path.join(a, "logs", "s.json"), "w").write("old")
        self.run_in(a, "save", "sweep")
        b = self.checkout("w2"); os.makedirs(os.path.join(b, "logs"))
        open(os.path.join(b, "logs", "s.json"), "w").write("new")
        self.run_in(b, "restore")
        self.assertEqual(open(os.path.join(b, "logs", "s.json")).read(), "new")

    def test_unreachable_vault_is_fail_safe(self):
        a = self.checkout("down")
        env = dict(os.environ, PRIVATE_STATE_REPO="file://" + os.path.join(self.d, "missing.git"), HELPMAP_STATE_KEY="k",
                   GITHUB_REF="refs/heads/main", PRIVATE_STATE_RETRY_WAIT="0", PRIVATE_STATE_WORK=os.path.join(self.d, "work-down"))
        r = subprocess.run(["bash", SCRIPT, "restore"], cwd=a, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("starting without saved state", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(a, "logs")))
        os.makedirs(os.path.join(a, "logs")); open(os.path.join(a, "logs", "x.json"), "w").write("{}")
        env["PRIVATE_STATE_WORK"] = os.path.join(self.d, "work-down2")
        r = subprocess.run(["bash", SCRIPT, "save", "sweep"], cwd=a, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("state not saved this run", r.stdout)

    # (a) times auto-apply is off unless real saved state came back
    def test_restore_flag_only_with_real_state(self):
        a = self.checkout("f1")
        self.run_in(a, "restore"); self.assertFalse(self.restored_flag())          # empty vault
        self.write(a, "logs/private_state_probe.json", "{}"); self.run_in(a, "save", "foodbanks")
        b = self.checkout("f2")
        r = self.run_in(b, "restore"); self.assertFalse(self.restored_flag(), r.stdout)   # probe only is not state
        self.assertIn("times auto-apply is off", r.stdout)
        self.write(b, "reports/times_auto_applied.json", "[]"); self.run_in(b, "save", "foodbanks")
        c = self.checkout("f3")
        r = self.run_in(c, "restore"); self.assertTrue(self.restored_flag(), r.stdout)
        d = self.checkout("f4"); self.run_in(d, "restore", key=""); self.assertFalse(self.restored_flag())

    def test_unreachable_vault_sets_no_flag(self):
        a = self.checkout("f5")
        self.remote = os.path.join(self.d, "gone.git")
        r = self.run_in(a, "restore")
        self.assertEqual(r.returncode, 0); self.assertFalse(self.restored_flag())
        self.assertIn("times auto-apply is off", r.stdout)

    # (b) one folder per layer, newest save wins for shared files, undo logs are merged, refused push retried
    def test_layers_saved_in_own_folders_and_merged_on_restore(self):
        a = self.checkout("fb"); b = self.checkout("sh")
        self.run_in(a, "restore"); self.run_in(b, "restore")          # both start before either saves (parallel)
        self.write(a, "reports/times_auto_applied.json", '[{"id": "fb1"}]'); self.write(a, "reports/learning_state.json", "old")
        self.write(b, "reports/times_auto_applied.json", '[{"id": "sh1"}, {"id": "fb1", "reverted": true}]')
        self.write(b, "logs/shelters_log.json", "{}")
        self.assertIn("saved", self.run_in(a, "save", "foodbanks").stdout)
        import time; time.sleep(1.1)
        self.write(b, "reports/learning_state.json", "new")
        self.assertIn("saved", self.run_in(b, "save", "shelters").stdout)
        files = self.vault_files()
        self.assertIn("site-run-state/foodbanks/reports/times_auto_applied.json", files)
        self.assertIn("site-run-state/shelters/reports/times_auto_applied.json", files)
        self.assertIn("site-run-state/shelters/logs/shelters_log.json", files)
        self.assertFalse([f for f in files if f.startswith(("site-run-state/logs/", "site-run-state/reports/"))])
        c = self.checkout("next"); self.run_in(c, "restore")
        import json
        undo = json.load(open(os.path.join(c, "reports", "times_auto_applied.json")))
        self.assertEqual(sorted(e["id"] for e in undo), ["fb1", "sh1"])
        self.assertTrue(next(e for e in undo if e["id"] == "fb1").get("reverted"))   # reverted anywhere stays reverted
        self.assertEqual(open(os.path.join(c, "reports", "learning_state.json")).read(), "new")

    def test_refused_push_is_retried_on_newest_copy(self):
        hook = os.path.join(self.remote, "hooks", "pre-receive")
        open(hook, "w").write('#!/bin/sh\nif [ ! -f "$GIT_DIR/once" ]; then touch "$GIT_DIR/once"; exit 1; fi\n')
        os.chmod(hook, 0o755)
        a = self.checkout("retry"); self.run_in(a, "restore")
        self.write(a, "logs/x.json", "{}")
        r = self.run_in(a, "save", "warmspaces")
        self.assertIn("push refused (try 1)", r.stdout); self.assertIn("saved 1", r.stdout)
        self.assertIn("site-run-state/warmspaces/logs/x.json", self.vault_files())

    # (d) the sweep has no practice mode (rule 94): its sync is proved here
    def test_sweep_sync_round_trip(self):
        a = self.checkout("sweep1"); self.run_in(a, "restore")
        self.write(a, "logs/discovery_today_sweep.json", '{"n": 3}'); self.write(a, "reports/learning_state.json", "{}")
        self.assertIn("saved 2", self.run_in(a, "save", "sweep").stdout)
        self.assertIn("site-run-state/sweep/logs/discovery_today_sweep.json", self.vault_files())
        b = self.checkout("sweep2"); r = self.run_in(b, "restore")
        self.assertIn("restored 2", r.stdout); self.assertTrue(self.restored_flag())
        self.assertEqual(open(os.path.join(b, "logs", "discovery_today_sweep.json")).read(), '{"n": 3}')
        self.assertNotIn('"n": 3', r.stdout + r.stderr)

    def test_unknown_label_refused(self):
        a = self.checkout("bad"); r = self.run_in(a, "save", "../escape")
        self.assertEqual(r.returncode, 2); self.assertEqual(self.vault_files(), [])


class TimesAutoApplyNeedsState(unittest.TestCase):
    """(a) In the refresh and sweep workflows, no restored state means no automatic opening-times changes."""
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import auto_rules; self.ar = auto_rules
        self.old = {k: os.environ.get(k) for k in ("HELPMAP_STATE_CHECK", "HELPMAP_STATE_RESTORED")}

    def tearDown(self):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def set(self, check, restored):
        for k, v in (("HELPMAP_STATE_CHECK", check), ("HELPMAP_STATE_RESTORED", restored)):
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def test_switch(self):
        on = {"times_auto_apply": True}
        self.set("1", None); self.assertFalse(self.ar.times_auto_allowed(on))
        self.set("1", "0"); self.assertFalse(self.ar.times_auto_allowed(on))
        self.set("1", "1"); self.assertTrue(self.ar.times_auto_allowed(on))
        self.set(None, None); self.assertTrue(self.ar.times_auto_allowed(on))       # local runs and tests unchanged
        self.set("1", "1"); self.assertFalse(self.ar.times_auto_allowed({"times_auto_apply": False}))

    def test_both_apply_paths_use_the_switch(self):
        tf = open(os.path.join(ROOT, "scripts", "times_finder.py"), encoding="utf-8").read()
        self.assertRegex(tf, r"def times_auto_on\(rules=None\): return auto_rules\.times_auto_allowed\(")
        dc = open(os.path.join(ROOT, "scripts", "discover.py"), encoding="utf-8").read()
        body = dc[dc.index("def times_gate_apply("):]
        body = body[:body.index("\ndef ")]
        self.assertIn("on = _ar.times_auto_allowed(rules)", body)
        self.assertNotIn('rules.get("times_auto_apply"', body)

    def test_workflows_require_state(self):
        for name in WORKFLOWS:
            wf = yaml.safe_load(open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8"))
            self.assertEqual(str(wf.get("env", {}).get("HELPMAP_STATE_CHECK")), "1", name)
            for job in wf["jobs"].values():
                self.assertNotIn("HELPMAP_STATE_CHECK", str(job.get("env", {})), name)
                for s in job["steps"]:
                    self.assertNotIn("HELPMAP_STATE_CHECK", str(s.get("env", {})), name)
                    self.assertNotIn("HELPMAP_STATE_RESTORED", str(s.get("env", {})), name)
                    if "private_state.sh" not in s.get("run", ""):
                        self.assertNotIn("HELPMAP_STATE_RESTORED", s.get("run", ""), name)


class NeverStagedForPublic(unittest.TestCase):
    """(c) Restored logs/ and reports/ never reach the public repo's index."""
    def test_gitignore_keeps_them_out(self):
        lines = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().split()
        self.assertIn("logs/", lines); self.assertIn("reports/", lines)

    def test_publish_add_skips_restored_files(self):
        d = tempfile.mkdtemp()
        try:
            subprocess.run(["git", "init", "-q", d], check=True)
            shutil.copy(os.path.join(ROOT, ".gitignore"), d)
            for rel in ("logs/times_finder_seen.json", "reports/times_auto_applied.json", "reports/learning_state.json"):
                os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True); open(os.path.join(d, rel), "w").write("{}")
            open(os.path.join(d, "stamp.js"), "w").write("x")
            subprocess.run(["bash", os.path.join(ROOT, "scripts", "git_add_existing.sh"), "stamp.js",
                            "logs/times_finder_seen.json", "reports/times_auto_applied.json", "reports/learning_state.json"],
                           cwd=d, capture_output=True, check=True)
            staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=d, capture_output=True, text=True).stdout.split()
            self.assertEqual(staged, ["stamp.js"])
            st = subprocess.run(["git", "status", "--porcelain"], cwd=d, capture_output=True, text=True).stdout
            self.assertNotRegex(st, r"(^|\s)(logs|reports)/")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_workflows_never_force_add_or_add_logs_directly(self):
        import re
        for name in WORKFLOWS:
            for s in steps(name):
                for line in s.get("run", "").splitlines():
                    for cmd in re.split(r"[;&|]+", line):
                        m = re.search(r"\bgit\s+add\b(.*)", cmd)
                        if not m: continue
                        self.assertNotRegex(m.group(1), r"(^|\s)(-f|--force)\b", name)
                        self.assertNotRegex(m.group(1), r"(^|\s)(logs|reports)(/|\s|$)", name)


if __name__ == "__main__":
    unittest.main()
