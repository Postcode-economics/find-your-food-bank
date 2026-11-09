"""Private run state (rule 97): logs/ and reports/ persist between runs only through the private vault repo.

Locks in: each refresh and the deep sweep restores saved state right after checkout and saves it only on main,
using the HELPMAP_STATE_KEY secret; nothing internal is uploaded as an artifact of this public repo; the script
never prints file contents; and a round trip through a local stand-in repo restores exactly what was saved."""
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
        env = dict(os.environ, PRIVATE_STATE_REPO="file://" + self.remote, HELPMAP_STATE_KEY=key, GITHUB_REF=ref,
                   PRIVATE_STATE_WORK=os.path.join(self.d, "work-" + os.path.basename(cwd)))
        return subprocess.run(["bash", SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True)

    def checkout(self, name):
        p = os.path.join(self.d, name); os.makedirs(p); return p

    def test_save_then_restore(self):
        a = self.checkout("run1")
        self.assertIn("restored 0", self.run_in(a, "restore").stdout)
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
        self.assertIn("restored 0", self.run_in(b, "restore").stdout)

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


if __name__ == "__main__":
    unittest.main()
