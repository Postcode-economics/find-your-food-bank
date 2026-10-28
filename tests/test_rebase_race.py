"""Reproduces the 28 Oct race: a sweep starts on pre-PR main, restamps faq.html,
then `git pull --rebase` over the merged PR conflicts. The conflict script must keep
main's page (rebuilt afterwards by build_seo/seo_meta), never the run's stale copy."""
import os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rebase_resolve as rr


def g(cwd, *a, check=True):
    return subprocess.run(["git", *a], cwd=cwd, check=check, capture_output=True, text=True)


class RebaseRace(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.origin = os.path.join(self.d, "origin.git")
        g(self.d, "init", "-q", "--bare", "-b", "main", self.origin)
        self.pr = self._clone("pr")
        os.makedirs(os.path.join(self.pr, "scripts"))
        os.makedirs(os.path.join(self.pr, "reports"))
        for f in ("refresh_rebase_conflicts.sh", "rebase_resolve.py"):
            shutil.copy(os.path.join(ROOT, "scripts", f), os.path.join(self.pr, "scripts", f))
        self._w(self.pr, "faq.html", "<p class=upd>Last updated 27 Oct</p>\n<b>SWEP:</b> checked on every refresh.\n")
        self._w(self.pr, "reports/pending_dean.md", "# Pending\n<!-- closures -->\n- none\n<!-- /closures -->\n")
        self._w(self.pr, "data.json", '{"n": 1}\n')
        self._commit(self.pr, "base"); g(self.pr, "push", "-q", "origin", "main")
        self.sweep = self._clone("sweep")  # sweep starts on pre-PR main

    def _clone(self, name):
        p = os.path.join(self.d, name)
        g(self.d, "clone", "-q", self.origin, p)
        g(p, "config", "user.email", "t@t"); g(p, "config", "user.name", "t")
        return p

    def _w(self, repo, f, s):
        with open(os.path.join(repo, f), "w", encoding="utf-8") as fh: fh.write(s)

    def _r(self, repo, f):
        with open(os.path.join(repo, f), encoding="utf-8") as fh: return fh.read()

    def _commit(self, repo, msg):
        g(repo, "add", "-A"); g(repo, "commit", "-q", "-m", msg)

    def test_sweep_cannot_revert_merged_pr(self):
        # PR merges new FAQ wording and a new report section
        self._w(self.pr, "faq.html", "<p class=upd>Last updated 27 Oct</p>\n<b>SWEP:</b> checked every day, on every refresh.\n")
        self._w(self.pr, "reports/pending_dean.md", "# Pending\n<!-- closures -->\n- none\n<!-- /closures -->\n<!-- phone lock -->\n- held kings-langley\n<!-- /phone lock -->\n")
        self._commit(self.pr, "PR #212"); g(self.pr, "push", "-q", "origin", "main")
        # sweep (started earlier) rewrites the whole page from its old copy + new data
        self._w(self.sweep, "faq.html", "<p class=upd>Last updated 28 Oct</p>\n<b>SWEP:</b> checked on every refresh, three times a day.\n")
        self._w(self.sweep, "reports/pending_dean.md", "# Pending\n<!-- closures -->\n- one closure\n<!-- /closures -->\n")
        self._w(self.sweep, "data.json", '{"n": 2}\n')
        self._commit(self.sweep, "Daily deep sweep")
        r = g(self.sweep, "pull", "-q", "--rebase", check=False)
        self.assertNotEqual(r.returncode, 0, "race not reproduced: expected a rebase conflict")
        subprocess.run(["bash", "scripts/refresh_rebase_conflicts.sh"], cwd=self.sweep, check=True, capture_output=True)
        g(self.sweep, "-c", "core.editor=true", "rebase", "--continue")
        faq = self._r(self.sweep, "faq.html")
        self.assertIn("checked every day, on every refresh", faq)       # PR's wording kept
        self.assertNotIn("three times a day", faq)                       # stale copy gone
        rep = self._r(self.sweep, "reports/pending_dean.md")
        self.assertIn("held kings-langley", rep)                         # PR's section kept
        self.assertIn("one closure", rep)                                # run's section kept
        self.assertEqual(self._r(self.sweep, "data.json"), '{"n": 2}\n')  # run's data kept


    def _race(self, base_extra, pr_text, run_text):
        r = g(self.sweep, "pull", "-q", "--rebase", check=False)
        self.assertNotEqual(r.returncode, 0, "race not reproduced: expected a rebase conflict")
        subprocess.run(["bash", "scripts/refresh_rebase_conflicts.sh"], cwd=self.sweep, check=True, capture_output=True)
        g(self.sweep, "-c", "core.editor=true", "rebase", "--continue")
        return self._r(self.sweep, "reports/pending_dean.md")

    def test_run_header_outside_sections_kept(self):
        # PR adds a section; the run rewrites the unsectioned header (new held places)
        self._w(self.pr, "reports/pending_dean.md", "# Pending\n<!-- phone lock -->\n- held kings-langley\n<!-- /phone lock -->\n<!-- closures -->\n- none\n<!-- /closures -->\n")
        self._commit(self.pr, "PR"); g(self.pr, "push", "-q", "origin", "main")
        self._w(self.sweep, "reports/pending_dean.md", "# Pending\n## warmspaces (1)\n- New Hall (AB1 2CD)\n<!-- closures -->\n- one closure\n<!-- /closures -->\n")
        self._commit(self.sweep, "sweep")
        rep = self._race(None, None, None)
        self.assertIn("- New Hall (AB1 2CD)", rep)          # run's header text kept
        self.assertIn("held kings-langley", rep)            # main's section kept
        self.assertIn("one closure", rep)                   # run's section kept
        self.assertLess(rep.index("New Hall"), rep.index("<!-- closures -->"))  # stays at top

    def test_main_header_change_kept_when_run_did_not_touch_it(self):
        self._w(self.pr, "reports/pending_dean.md", "# Pending (edited by PR)\n<!-- phone lock -->\n- held kings-langley\n<!-- /phone lock -->\n<!-- closures -->\n- none (checked by PR)\n<!-- /closures -->\n")
        self._commit(self.pr, "PR"); g(self.pr, "push", "-q", "origin", "main")
        self._w(self.sweep, "reports/pending_dean.md", "# Pending\n<!-- closures -->\n- one closure\n<!-- /closures -->\n")
        self._commit(self.sweep, "sweep")
        rep = self._race(None, None, None)
        self.assertIn("edited by PR", rep)
        self.assertIn("held kings-langley", rep)
        self.assertIn("one closure", rep)

    def test_section_removed_by_run_stays_removed(self):
        base = "# Pending\n<!-- closures -->\n- none\n<!-- /closures -->\n<!-- old -->\n- stale\n<!-- /old -->\n"
        self._w(self.pr, "reports/pending_dean.md", base); self._commit(self.pr, "base2"); g(self.pr, "push", "-q", "origin", "main")
        g(self.sweep, "pull", "-q", "--rebase")
        self._w(self.pr, "reports/pending_dean.md", base + "<!-- phone lock -->\n- held kings-langley\n<!-- /phone lock -->\n")
        self._commit(self.pr, "PR"); g(self.pr, "push", "-q", "origin", "main")
        self._w(self.sweep, "reports/pending_dean.md", "# Pending\n<!-- closures -->\n- one closure\n<!-- /closures -->\n")
        self._commit(self.sweep, "sweep")
        rep = self._race(None, None, None)
        self.assertNotIn("<!-- old -->", rep)
        self.assertNotIn("stale", rep)
        self.assertIn("held kings-langley", rep)
        self.assertIn("one closure", rep)

    def test_merge_sections_unit(self):
        base = "H\n<!-- a -->\nA\n<!-- /a -->\n<!-- b -->\nB\n<!-- /b -->\n"
        ours = "H\n<!-- a -->\nA\n<!-- /a -->\n<!-- b -->\nB2\n<!-- /b -->\n"   # main edited b
        theirs = "H run\n<!-- c -->\nC\n<!-- /c -->\n"                          # run removed a and b
        out = rr.merge_sections(base, ours, theirs)
        self.assertTrue(out.startswith("H run\n"))
        self.assertNotIn("<!-- a -->", out)   # untouched by main: stays removed
        self.assertIn("B2", out)              # main's edit never lost
        self.assertIn("<!-- c -->\nC\n<!-- /c -->", out)

    def test_classification(self):
        for f in ("faq.html", "food-banks/x/index.html", "warm-spaces/a/index.html", "shelters/b/index.html",
                  "sitemap.xml", "overrides/page_dates.json", "index.html"):
            self.assertTrue(rr.is_generated(f), f)
        for f in ("data.js", "overrides/opening_times.json", "reports/pending_dean.md", "logs/x.json"):
            self.assertFalse(rr.is_generated(f), f)

    def test_workflows_rebuild_after_conflicts(self):
        for rel in ("refresh.yml", "refresh-shelters.yml", "refresh-warmspaces.yml", "sweep-daily.yml"):
            y = self._r(ROOT, os.path.join(".github", "workflows", rel))
            i = y.find("refresh_rebase_conflicts.sh")
            self.assertGreater(i, 0, rel)
            self.assertIn("seo_meta.py", y[i:], rel)


if __name__ == "__main__":
    unittest.main()
