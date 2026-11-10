"""Every refresh and the deep sweep run their lock and verification tests again AFTER the rebuild and BEFORE
the commit, so a rebuild that breaks a test is never published. Plain unittest: the refreshes run
`python -m unittest discover`, which has no pytest installed."""
import os, subprocess, sys, unittest

try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")
VENV = "python -m venv /tmp/postcheck && /tmp/postcheck/bin/"
# workflow: (job, rebuild command, commit step name)
WORKFLOWS = {
    "refresh.yml": ("refresh", "python scripts/build.py", "Commit if changed"),
    "refresh-shelters.yml": ("refresh", "python scripts/build_shelters.py", "Commit if changed"),
    "refresh-warmspaces.yml": ("refresh", "python scripts/build_warmspaces.py", "Commit if changed"),
    "sweep-daily.yml": ("sweep", "python scripts/sweep_daily.py", "Commit new entries and the sweep log"),
}


def steps(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data["jobs"][WORKFLOWS[name][0]]["steps"]


def index(st, pred):
    hits = [i for i, s in enumerate(st) if pred(s)]
    return hits[0] if hits else -1


class PostRebuildChecks(unittest.TestCase):
    def test_same_checks_rerun_after_rebuild_before_commit(self):
        for name, (_, rebuild, commit) in WORKFLOWS.items():
            with self.subTest(workflow=name):
                st = steps(name)
                run = lambda s: str(s.get("run") or "")
                pre = index(st, lambda s: "-m unittest" in run(s) and VENV not in run(s) and "council-area" not in run(s))
                build = index(st, lambda s: run(s).strip().startswith(rebuild))
                post = index(st, lambda s: run(s).startswith(VENV))
                com = index(st, lambda s: s.get("name") == commit)
                self.assertGreaterEqual(pre, 0, "pre-rebuild test step missing")
                self.assertGreaterEqual(post, 0, "post-rebuild check step was removed")
                self.assertLess(pre, build)
                self.assertLess(build, post)
                self.assertEqual(post + 1, com, "the post-rebuild check must be the step right before the commit")
                # Exactly the same test set as before the rebuild, never a smaller one (rule 34).
                self.assertEqual(run(st[post])[len(VENV):].strip(), run(st[pre]).strip())
                # It must be able to stop the publish: no continue-on-error, no condition that could skip it.
                self.assertNotIn("continue-on-error", st[post])
                self.assertNotIn("if", st[post])
                self.assertNotIn("|| true", run(st[post]))


class TestStepsIgnoreTheRunsUndoBaseline(unittest.TestCase):
    """private_state.sh restore puts HELPMAP_UNDO_BASELINE(_ROOT) in GITHUB_ENV for the anomaly brake. A test step that
    inherits them makes every test that runs full_check.main() count this run's real refresh-gate times (practice
    42813119765: test_brake_gaps saw 7 changes, not 0). Every unittest step blanks both, which step env does over GITHUB_ENV."""
    def test_every_unittest_step_blanks_the_baseline(self):
        for name in WORKFLOWS:
            for s in steps(name):
                if "-m unittest" not in str(s.get("run") or ""): continue
                with self.subTest(workflow=name, step=s.get("name")):
                    env = s.get("env") or {}
                    self.assertEqual(env.get("HELPMAP_UNDO_BASELINE"), "")
                    self.assertEqual(env.get("HELPMAP_UNDO_BASELINE_ROOT"), "")


if __name__ == "__main__":
    unittest.main()
