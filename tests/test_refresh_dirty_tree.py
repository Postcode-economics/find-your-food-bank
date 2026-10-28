"""27 Oct 21:06 refresh (run 40583907794) failed: a tracked file a step rewrote was not in the add list, the
tree stayed dirty, and 'git pull --rebase' refused all 3 attempts ('no rebase in progress' for the conflict script).
These checks keep the guards in every workflow that commits and pulls onto main."""
import os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")
PUSHERS = ["refresh.yml", "refresh-shelters.yml", "refresh-warmspaces.yml", "sweep-daily.yml"]


def commit_step(name):
    s = open(os.path.join(WF, name)).read()
    i = s.index("git commit -m")
    return s, s[s.rindex("run: |", 0, i):s.index("exit 1", i)]


def add_list(step):
    m = re.search(r"\n\s*bash scripts/git_add_existing\.sh (.*?)\n\s*if git diff --cached --quiet", step, re.S)
    lines = [l for l in m.group(1).split("\n") if not l.strip().startswith("#")]
    return "\n".join(lines).replace("\\\n", " ").split()


def covered(path, paths):
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths)


class DirtyTreeGuards(unittest.TestCase):
    def test_every_pull_autostashes(self):
        for n in PUSHERS:
            _, step = commit_step(n)
            pulls = re.findall(r"^\s*(?:if )?git pull[^;\n]*", step, re.M)
            self.assertTrue(pulls, n)
            for p in pulls:
                self.assertIn("--rebase", p, n)
                self.assertIn("--autostash", p, n)

    def test_status_printed_and_leftovers_stashed_before_pull(self):
        for n in PUSHERS:
            _, step = commit_step(n)
            c, pull = step.index("git commit -m"), step.index("for n in 1 2 3")
            between = step[c:pull]
            self.assertIn("git status", between, n)
            self.assertIn("git diff --name-only HEAD", between, n)
            self.assertIn("git stash push", between, n)
            self.assertIn("git ls-files --others --exclude-standard", between, n)
            self.assertIn("git stash push --include-untracked", between, n)

    def test_publish_list_tolerates_missing_paths_and_every_path_is_seeded(self):
        tracked = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split())
        for n in PUSHERS:
            _, step = commit_step(n)
            paths = add_list(step)
            self.assertGreater(len(paths), 10, n)
            for p in paths:
                self.assertTrue(p.rstrip("/") in tracked or any(t.startswith(p.rstrip("/") + "/") for t in tracked),
                                n + ": " + p + " is not committed, so a run that does not write it would have nothing to add")

    def _repo(self, d):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        return lambda cmd, cwd: subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True, text=True)

    def test_add_helper_skips_a_missing_path_and_stages_the_rest(self):
        if not shutil.which("git") or not shutil.which("bash"):
            self.skipTest("git/bash missing")
        helper = os.path.join(ROOT, "scripts", "git_add_existing.sh")
        d = tempfile.mkdtemp()
        try:
            sh = self._repo(d)
            sh("git init -q -b main && mkdir logs && echo 1 > gone.txt && echo 1 > data.js && git add . && git commit -qm init", d)
            self.assertNotEqual(sh("echo 2 > data.js && git add data.js logs/never_written.json", d).returncode, 0)
            self.assertEqual(sh("git diff --cached --name-only", d).stdout, "")  # plain git add staged nothing
            r = sh("rm gone.txt && echo 1 > logs/new.json && bash " + helper + " data.js logs/never_written.json gone.txt logs/", d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("logs/never_written.json", r.stdout)
            self.assertEqual(sorted(sh("git diff --cached --no-renames --name-status", d).stdout.splitlines()),
                             ["A\tlogs/new.json", "D\tgone.txt", "M\tdata.js"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_guard_lets_pull_succeed_when_an_untracked_file_was_committed_upstream(self):
        if not shutil.which("git") or not shutil.which("bash"):
            self.skipTest("git/bash missing")
        _, step = commit_step("refresh.yml")
        c = step.index("\n", step.index("git commit -m"))
        guard = "\n".join(l.strip() for l in step[c:step.index("for n in 1 2 3")].splitlines())
        d = tempfile.mkdtemp()
        try:
            sh = self._repo(d)
            sh("git init -q --bare -b main origin.git && git clone -q origin.git a 2>/dev/null && cd a && mkdir logs && echo 1 > data.js && git add . && git commit -qm init && git push -q origin HEAD:main && cd .. && git clone -q origin.git b && cd b && mkdir -p logs && echo other > logs/area.json && git add . && git commit -qm other && git push -q", d)
            a = os.path.join(d, "a")
            sh("git branch -u origin/main 2>/dev/null; echo 2 > data.js && echo mine > logs/area.json && git add data.js && git commit -qm run", a)
            r0 = sh("git pull --rebase --autostash", a)
            self.assertNotEqual(r0.returncode, 0)
            self.assertIn("untracked working tree files would be overwritten", r0.stdout + r0.stderr)
            r = sh(guard + "\ngit pull --rebase --autostash", a)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("logs/area.json", r.stdout)
            self.assertEqual(open(os.path.join(a, "logs", "area.json")).read().strip(), "other")
            self.assertEqual(open(os.path.join(a, "data.js")).read().strip(), "2")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_conflict_script_only_inside_a_rebase(self):
        for n in PUSHERS:
            _, step = commit_step(n)
            self.assertIn("in_rebase()", step, n)
            self.assertIn("rebase-merge", step, n)
            self.assertIn("rebase-apply", step, n)
            for line in step.splitlines():
                if "refresh_rebase_conflicts.sh" in line and "in_rebase" not in line:
                    prev = step[:step.index(line)].rstrip().splitlines()[-1]
                    self.assertIn("if in_rebase", prev, n + ": " + line.strip())

    def test_sense_check_outputs_are_published(self):
        for n in PUSHERS:
            s, step = commit_step(n)
            if "scripts/sense_check.py" not in s:
                continue
            paths = add_list(step)
            for f in ("logs/sense_check.json", "reports/sense_check.md"):
                self.assertTrue(covered(f, paths), n + " misses " + f)

    def test_guard_lets_pull_succeed_on_a_dirty_tree(self):
        if not shutil.which("git") or not shutil.which("bash"):
            self.skipTest("git/bash missing")
        _, step = commit_step("refresh.yml")
        c = step.index("\n", step.index("git commit -m"))
        guard = "\n".join(l.strip() for l in step[c:step.index("for n in 1 2 3")].splitlines())
        d = tempfile.mkdtemp()
        try:
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
            sh = lambda cmd, cwd: subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True, text=True)
            sh("git init -q --bare -b main origin.git && git clone -q origin.git a 2>/dev/null && cd a && mkdir logs && echo 1 > logs/sense_check.json && echo 1 > data.js && git add . && git commit -qm init && git push -q origin HEAD:main && cd .. && git clone -q origin.git b && cd b && echo 2 > other.txt && git add . && git commit -qm other && git push -q", d)
            a = os.path.join(d, "a")
            sh("git branch -u origin/main 2>/dev/null; echo 2 > data.js && echo 2 > logs/sense_check.json && git add data.js && git commit -qm run", a)
            self.assertNotEqual(sh("git pull --rebase", a).returncode, 0)  # the 27 Oct failure
            r = sh(guard + "\ngit pull --rebase --autostash", a)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("logs/sense_check.json", r.stdout)
            self.assertTrue(os.path.exists(os.path.join(a, "other.txt")))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
