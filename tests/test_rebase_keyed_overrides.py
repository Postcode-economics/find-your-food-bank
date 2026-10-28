"""overrides/opening_times.json and reports/phone_fixes.json are merged key by key on a rebase conflict, so a refresh
or sweep that started before Dean's hand edit or a revert on main never puts back its stale copy of the whole file."""
import json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rebase_resolve as rr

OT, PF = "overrides/opening_times.json", "reports/phone_fixes.json"
A = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am - 12pm", "source_url": "https://a.org/"}
U = "https://www.riverside-fb.org.uk/"
FIX = {"old": "01234000000", "new": "01234500001", "since": "2026-10-27", "source": U}
J = json.dumps


def g(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *a], cwd=cwd, check=check, capture_output=True, text=True)


class Config(unittest.TestCase):
    def test_both_files_are_keyed_and_marked_for_the_json_merge(self):
        attrs = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read().split("\n")
        for f in (OT, PF):
            self.assertIn(f, rr.KEYED); self.assertIn(f + " -merge", attrs)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "reports")); os.makedirs(os.path.join(self.d, "overrides"))
        self.orig = (rr.ROOT, rr.stage, rr.git); self.added = []
        rr.ROOT = self.d; rr.git = lambda *a, **k: self.added.append(a)
    def tearDown(self): rr.ROOT, rr.stage, rr.git = self.orig
    def stages(self, base, ours, theirs): rr.stage = lambda f, n: {1: base, 2: ours, 3: theirs}[n]

    def test_opening_times_keeps_deans_hand_edit_and_the_runs_new_times(self):
        base = {"fb1": A, "fb2": dict(A, source_url="https://b.org/")}
        main = dict(base, fb2=dict(A, raw="Hand checked by Dean", protected=True))       # Dean edits fb2 on main
        run = dict(base, fb3=dict(A, source_url="https://c.org/"))                         # the run adds fb3
        self.stages(J(base), J(main), J(run))
        self.assertEqual(rr.resolve(OT), "json-merge")
        text = open(os.path.join(self.d, OT), encoding="utf-8").read()
        self.assertEqual(json.loads(text), dict(main, fb3=run["fb3"]))
        self.assertEqual(text, json.dumps(dict(main, fb3=run["fb3"]), indent=1, sort_keys=True, ensure_ascii=False))
        self.assertIn(("add", "--", OT), self.added)

    def test_opening_times_revert_on_main_is_not_put_back(self):
        """times_revert.py on main removed fb1; the run (started before) still has it unchanged."""
        base = {"fb1": A, "fb2": A}
        self.stages(J(base), J({"fb2": A}), J(dict(base, fb2=dict(A, raw="Wednesday 10am - 12.30pm"))))
        rr.resolve(OT)
        self.assertEqual(json.load(open(os.path.join(self.d, OT))), {"fb2": dict(A, raw="Wednesday 10am - 12.30pm")})

    def test_phone_fixes_keeps_mains_revert_and_the_runs_new_fix(self):
        other = "https://other.org/"
        base = {U: FIX}
        self.stages(J(base), J({}), J({U: FIX, other: dict(FIX, source=other)}))
        rr.resolve(PF)
        text = open(os.path.join(self.d, PF), encoding="utf-8").read()
        self.assertEqual(json.loads(text), {other: dict(FIX, source=other)})
        self.assertEqual(text, json.dumps({other: dict(FIX, source=other)}, indent=1, ensure_ascii=False))


class RebaseRace(unittest.TestCase):
    """A real git pull --rebase through scripts/refresh_rebase_conflicts.sh, as the workflows run it."""
    def setUp(self):
        if not shutil.which("git"): self.skipTest("git missing")
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        origin = os.path.join(self.d, "origin.git")
        g(self.d, "init", "-q", "--bare", "-b", "main", origin)
        self.main = self._clone(origin, "main")
        for x in ("scripts", "reports", "overrides"): os.makedirs(os.path.join(self.main, x))
        for f in ("refresh_rebase_conflicts.sh", "rebase_resolve.py"):
            shutil.copy(os.path.join(ROOT, "scripts", f), os.path.join(self.main, "scripts", f))
        shutil.copy(os.path.join(ROOT, ".gitattributes"), self.main)
        self._w(self.main, OT, {"fb1": A, "fb2": A}); self._w(self.main, PF, {U: FIX})
        g(self.main, "add", "-A"); g(self.main, "commit", "-q", "-m", "base"); g(self.main, "push", "-q", "origin", "main")
        self.run_ = self._clone(origin, "run")

    def _clone(self, origin, name):
        p = os.path.join(self.d, name)
        g(self.d, "clone", "-q", origin, p); g(p, "config", "user.email", "t@t"); g(p, "config", "user.name", "t")
        return p

    def _w(self, repo, f, obj):
        with open(os.path.join(repo, f), "w", encoding="utf-8") as fh: json.dump(obj, fh, indent=1, sort_keys=True)

    def _r(self, repo, f):
        return json.load(open(os.path.join(repo, f), encoding="utf-8"))

    def test_overlapping_run_keeps_mains_edits(self):
        hand = dict(A, raw="Hand checked", protected=True)
        self._w(self.main, OT, {"fb1": A, "fb2": hand}); self._w(self.main, PF, {})
        g(self.main, "commit", "-qam", "Dean: hand edit + phone revert"); g(self.main, "push", "-q")
        new = dict(A, source_url="https://c.org/")
        self._w(self.run_, OT, {"fb1": A, "fb2": A, "fb3": new})
        self._w(self.run_, PF, {U: FIX, "https://other.org/": FIX})
        g(self.run_, "commit", "-qam", "sweep")
        r = g(self.run_, "pull", "-q", "--rebase", check=False)
        self.assertNotEqual(r.returncode, 0, "expected the -merge attribute to make this a conflict")
        shim = os.path.join(self.d, "bin"); os.makedirs(shim)
        os.symlink(sys.executable, os.path.join(shim, "python"))
        env = dict(os.environ, PATH=shim + os.pathsep + os.environ.get("PATH", ""))
        out = subprocess.run(["bash", "scripts/refresh_rebase_conflicts.sh"], cwd=self.run_, capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(out.stdout.count("json-merge"), 2, out.stdout)
        g(self.run_, "-c", "core.editor=true", "rebase", "--continue")
        self.assertEqual(self._r(self.run_, OT), {"fb1": A, "fb2": hand, "fb3": new})
        self.assertEqual(self._r(self.run_, PF), {"https://other.org/": FIX})
        self.assertEqual(g(self.run_, "status", "--porcelain").stdout, "")


if __name__ == "__main__": unittest.main()
