"""Gaps: rebase_resolve.resolve() on the phone undo log / undone map (format + staged), merge_keyed edge cases,
git_add_existing.sh edge cases, and every workflow publishes the automatic-change state its scripts write."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rebase_resolve as rr
J = json.dumps
U = "https://www.riverside-fb.org.uk/"
P1 = {"website": U, "old": "01234000000", "new": "01234500001", "source_url": U, "first_run_at": "r1", "second_run_at": "r2", "revert": "python scripts/phone_revert.py " + U}
P2 = dict(P1, website="https://other.org/", revert="python scripts/phone_revert.py https://other.org/")


class Resolve(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "reports")); os.makedirs(os.path.join(self.d, "overrides"))
        self.orig = (rr.ROOT, rr.stage, rr.git); self.added = []
        rr.ROOT = self.d; rr.git = lambda *a, **k: self.added.append(a)
    def tearDown(self): rr.ROOT, rr.stage, rr.git = self.orig
    def stages(self, base, ours, theirs): rr.stage = lambda f, n: {1: base, 2: ours, 3: theirs}[n]

    def test_phone_undo_log_keeps_main_revert_and_run_entry(self):
        f = "reports/phone_auto_applied.json"
        self.stages(J([P1]), J([dict(P1, reverted=True)]), J([P1, P2]))
        self.assertEqual(rr.resolve(f), "json-merge")
        self.assertEqual(json.load(open(os.path.join(self.d, f))), [dict(P1, reverted=True), P2])
        self.assertIn(("add", "--", f), self.added)

    def test_phone_undone_map_keeps_deans_block_and_is_sorted(self):
        f = "overrides/phone_auto_undone.json"
        self.stages(J({}), J({U: "01234500001"}), J({"https://z.org/": "01111111111"}))
        self.assertEqual(rr.resolve(f), "json-merge")
        text = open(os.path.join(self.d, f)).read()
        self.assertEqual(json.loads(text), {U: "01234500001", "https://z.org/": "01111111111"})
        self.assertLess(text.index(U), text.index("https://z.org/"))

    def test_file_new_on_both_sides(self):
        f = "reports/times_auto_applied.json"
        self.stages(None, J([{"id": "a"}]), J([{"id": "b"}]))
        rr.resolve(f)
        self.assertEqual(json.load(open(os.path.join(self.d, f))), [{"id": "a"}, {"id": "b"}])


class Keyed(unittest.TestCase):
    def test_both_sides_changed_one_key_the_run_wins(self):
        out = rr.merge_keyed(J({"k": 1}), J({"k": 2}), J({"k": 3}))
        self.assertEqual(out, {"k": 3})

    def test_main_deleted_a_key_the_run_left_alone_stays_deleted(self):
        self.assertEqual(rr.merge_keyed(J({"k": 1, "j": 1}), J({"j": 1}), J({"k": 1, "j": 1})), {"j": 1})

    def test_run_dropped_a_key_main_changed_keeps_main(self):
        self.assertEqual(rr.merge_keyed(J({"k": 1}), J({"k": 2}), J({})), {"k": 2})


class AddHelper(unittest.TestCase):
    def sh(self, cmd, cwd):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        return subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, capture_output=True, text=True)

    def setUp(self):
        if not shutil.which("git"): self.skipTest("git missing")
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        self.h = os.path.join(ROOT, "scripts", "git_add_existing.sh")
        self.sh("git init -q -b main && mkdir -p export && echo 1 > export/a.csv && echo 1 > k && git add . && git commit -qm i", self.d)

    def test_every_path_missing_is_not_an_error(self):
        r = self.sh("bash %s nope1 logs/nope2.json" % self.h, self.d)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stdout.count("::warning::"), 2)
        self.assertEqual(self.sh("git diff --cached --name-only", self.d).stdout, "")

    def test_a_tracked_directory_deleted_on_disk_stages_its_removal(self):
        r = self.sh("rm -rf export && bash %s export/ k" % self.h, self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sh("git diff --cached --name-status", self.d).stdout.split("\n")[0], "D\texport/a.csv")


def add_list(wf):
    s = open(os.path.join(ROOT, ".github", "workflows", wf)).read()
    i = s.index("git commit -m"); step = s[s.rindex("run: |", 0, i):i]
    m = re.search(r"bash scripts/git_add_existing\.sh (.*?)\n\s*if git diff --cached --quiet", step, re.S)
    return s, m.group(1).replace("\\\n", " ").split()


class Publish(unittest.TestCase):
    WRITES = {  # script run by the workflow -> automatic-change state it writes
        "scripts/build.py": ["logs/times_crosscheck_seen.json", "reports/times_auto_applied.json"],
        "scripts/build_shelters.py": ["logs/times_crosscheck_seen.json", "reports/times_auto_applied.json"],
        "scripts/build_warmspaces.py": ["logs/times_crosscheck_seen.json", "reports/times_auto_applied.json", "logs/warmspaces_carry_forward.json"],
        "scripts/times_finder.py": ["logs/times_finder_seen.json", "reports/times_auto_applied.json", "overrides/opening_times.json"],
        "scripts/full_check.py": ["reports/phone_auto_applied.json", "reports/phone_fixes.json"],
    }
    def test_every_workflow_publishes_the_state_its_scripts_write(self):
        for wf in ("refresh.yml", "refresh-shelters.yml", "refresh-warmspaces.yml", "sweep-daily.yml"):
            s, paths = add_list(wf)
            for script, files in self.WRITES.items():
                if "python " + script not in s: continue
                for f in files:
                    self.assertTrue(any(f == p or f.startswith(p.rstrip("/") + "/") for p in paths), "%s runs %s but does not publish %s" % (wf, script, f))

    def test_no_publish_path_is_gitignored(self):
        """git add exits 1 on an ignored path that exists, and the commit step runs under bash -e."""
        for wf in ("refresh.yml", "refresh-shelters.yml", "refresh-warmspaces.yml", "sweep-daily.yml"):
            _, paths = add_list(wf)
            r = subprocess.run(["git", "check-ignore", "--no-index", *paths], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "", wf)


if __name__ == "__main__": unittest.main()
