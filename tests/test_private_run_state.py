"""Private run state (rule 97): logs/ and reports/ persist between runs only through the private vault repo.

Locks in: each refresh and the deep sweep restores saved state right after checkout and saves it only on main,
using the HELPMAP_STATE_KEY secret; nothing internal is uploaded as an artifact of this public repo; the script
never prints file contents; and a round trip through a local stand-in repo restores exactly what was saved.
Grok Bot 2 on #491: (a) no restored state -> times auto-apply off for that run; (b) one private folder per layer,
undo logs merged, a refused push retried; (c) restored files are never staged for the public repo; (d) the sweep has
no practice mode (rule 94), so its sync is covered here by unit tests with the 'sweep' label."""
import os, re, shutil, subprocess, sys, tempfile, unittest
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
        # GITHUB_ENV is always a temp file here: inside a refresh's own test step the inherited one is the real run's,
        # and restore's start-of-run undo-log line would replace the run's real one (10 Nov practice 42798321225)
        env = dict(os.environ, PRIVATE_STATE_REPO="file://" + os.path.join(self.d, "missing.git"), HELPMAP_STATE_KEY="k",
                   GITHUB_REF="refs/heads/main", PRIVATE_STATE_RETRY_WAIT="0", PRIVATE_STATE_WORK=os.path.join(self.d, "work-down"),
                   GITHUB_ENV=os.path.join(self.d, "github_env-down"))
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


class SeenMemoryUnion(unittest.TestCase):
    """Two-run times memory survives the parallel layer saves: each layer's readings come back exactly as that layer
    saved them (signature, page and run time), whichever layer happened to save last. Synthetic ids only."""
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import private_state_restore; self.m = private_state_restore
        self.d = tempfile.mkdtemp(); self.src = os.path.join(self.d, "site-run-state"); self.n = 0

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def e(self, sig, run_at, url="https://example.org/times"):
        return {"run_at": run_at, "sig": sig, "source_url": url}

    def save(self, layer, rel, data, at=None):
        import json
        self.n += 1
        p = os.path.join(self.src, layer, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(data if isinstance(data, str) else json.dumps(data))
        open(os.path.join(self.src, layer, ".saved_at"), "w").write(str(at if at is not None else 1000 + self.n))

    def restored(self, rel="logs/times_crosscheck_seen.json", dst=None):
        import json
        dst = dst or os.path.join(self.d, "run-%d" % self.n); os.makedirs(dst, exist_ok=True)
        self.m.restore(self.src, dst)
        p = os.path.join(dst, rel)
        return json.load(open(p)) if os.path.exists(p) else None

    SEEN = "logs/times_crosscheck_seen.json"

    def test_parallel_layer_saves_keep_every_layers_readings(self):
        fb = self.e('{"mon": [["10:00", "12:00"]]}', "2026-01-05T05:52:54+00:00")
        sh = self.e('{"tue": [["09:00", "15:00"]]}', "2026-01-05T06:30:00+00:00")
        ws = self.e('{"wed": [["10:00", "14:00"]]}', "2026-01-05T06:05:24+00:00")
        # all three started before any saved, so each map holds only its own kind; the food bank run saves last
        self.save("warmspaces", self.SEEN, {"ws:test-hall": ws}, at=100)
        self.save("shelters", self.SEEN, {"sh:test-centre": sh}, at=200)
        self.save("foodbanks", self.SEEN, {"fb:test-bank": fb}, at=300)
        got = self.restored()
        self.assertEqual(got, {"fb:test-bank": fb, "sh:test-centre": sh, "ws:test-hall": ws})

    def test_owner_save_is_the_only_source_for_its_keys(self):
        old = self.e('{"mon": [["10:30", "13:30"]]}', "2026-01-04T12:41:00+00:00")
        new = self.e('{"mon": [["11:00", "13:00"]]}', "2026-01-05T04:41:00+00:00")
        # the food bank run carried an older shelter reading (and one the shelter run has since dropped) and saved later
        self.save("shelters", self.SEEN, {"sh:a": new}, at=200)
        self.save("foodbanks", self.SEEN, {"sh:a": old, "sh:dropped": old, "fb:x": old}, at=300)
        got = self.restored()
        self.assertEqual(got["sh:a"], new)                      # the shelter run's own reading, not the carried copy
        self.assertNotIn("sh:dropped", got)                     # a key the owner dropped never comes back as a first reading
        self.assertEqual(got["fb:x"], old)

    def test_owner_keeps_its_reading_even_when_another_copy_is_newer(self):
        mine = self.e("A", "2026-01-05T04:41:00+00:00")
        other = self.e("B", "2026-01-06T04:41:00+00:00")
        self.save("shelters", self.SEEN, {"sh:a": mine}, at=200)
        self.save("sweep", self.SEEN, {"sh:a": other}, at=300)
        self.assertEqual(self.restored()["sh:a"], mine)

    def test_without_an_owner_save_the_newest_reading_wins(self):
        older = self.e("A", "2026-01-04T04:41:00+00:00"); newer = self.e("B", "2026-01-05T04:41:00+00:00")
        self.save("foodbanks", self.SEEN, {"ws:a": newer}, at=100)    # saved first but holds the newer reading
        self.save("sweep", self.SEEN, {"ws:a": older}, at=200)
        self.assertEqual(self.restored()["ws:a"], newer)

    def test_unknown_folders_are_never_restored(self):
        archived = self.e("OLD", "2026-01-01T00:00:00+00:00")
        self.save("archive-2026-01-01", self.SEEN, {"sh:a": archived, "ws:b": archived}, at=999)
        self.save("archive-2026-01-01", "reports/learning_state.json", '{"keys": {"archived": 1}}', at=999)
        dst = os.path.join(self.d, "fresh"); os.makedirs(dst)
        n, ok = self.m.restore(self.src, dst)
        self.assertEqual((n, ok), (0, False))
        self.assertFalse(os.path.exists(os.path.join(dst, "logs"))); self.assertFalse(os.path.exists(os.path.join(dst, "reports")))

    def test_finder_memory_belongs_to_the_sweep(self):
        rel = "logs/times_finder_seen.json"
        mine = self.e("A", "2026-01-05T03:05:00+00:00"); stale = self.e("B", "2026-01-04T03:05:00+00:00")
        self.save("sweep", rel, {"bank-1": mine}, at=100)
        self.save("foodbanks", rel, {"bank-1": stale, "bank-2": stale}, at=200)
        self.assertEqual(self.restored(rel), {"bank-1": mine})

    def test_unreadable_owner_copy_never_falls_back_to_other_copies(self):
        """The owner saved the file, so it alone speaks for its keys: a copy that cannot be read or is not a map gives
        none of them, and another layer's older reading is never brought back as a first read."""
        carried = self.e("A", "2026-01-05T04:41:00+00:00"); fb = self.e("X", "2026-01-05T04:29:00+00:00")
        for bad in ("{not json", '{"sh:b": {"sig"', "[]", "null", '"text"', "7"):
            with self.subTest(owner_copy=bad):
                shutil.rmtree(self.src, ignore_errors=True)
                self.save("foodbanks", self.SEEN, {"sh:a": carried, "fb:x": fb}, at=200)
                self.save("shelters", self.SEEN, bad, at=300)
                self.assertEqual(self.restored(), {"fb:x": fb})

    def test_unreadable_owner_copy_saved_first_still_counts(self):
        carried = self.e("A", "2026-01-05T04:41:00+00:00")
        self.save("shelters", self.SEEN, "[]", at=100)
        self.save("foodbanks", self.SEEN, {"sh:a": carried}, at=200)
        self.assertEqual(self.restored(), {})

    def test_owner_saved_empty_map_gives_no_other_layers_keys(self):
        carried = self.e("A", "2026-01-05T04:41:00+00:00"); fb = self.e("X", "2026-01-05T04:29:00+00:00")
        self.save("foodbanks", self.SEEN, {"sh:a": carried, "fb:x": fb}, at=200)
        self.save("shelters", self.SEEN, {}, at=300)
        self.assertEqual(self.restored(), {"fb:x": fb})

    def test_every_copy_unreadable_restores_nothing(self):
        self.save("shelters", self.SEEN, "[]", at=100)
        self.save("foodbanks", self.SEEN, "{not json", at=200)
        self.assertIsNone(self.restored())

    def test_legacy_flat_copy_never_beats_the_owner(self):
        stale = self.e("OLD", "2026-01-04T04:41:00+00:00"); mine = self.e("B", "2026-01-05T04:41:00+00:00")
        fb = self.e("X", "2026-01-05T04:29:00+00:00")
        flat = os.path.join(self.src, self.SEEN); os.makedirs(os.path.dirname(flat), exist_ok=True)
        import json
        open(flat, "w").write(json.dumps({"sh:a": stale, "sh:b": self.e("OLDER", "2026-01-03T04:41:00+00:00")}))
        self.save("shelters", self.SEEN, {"sh:b": mine}, at=100)
        self.save("foodbanks", self.SEEN, {"fb:x": fb}, at=200)
        self.assertEqual(self.restored(), {"fb:x": fb, "sh:b": mine})

    def test_no_owner_tie_on_equal_run_time_goes_to_the_later_save(self):
        at = "2026-01-05T04:53:00+00:00"
        self.save("foodbanks", self.SEEN, {"ws:a": self.e("FIRST", at)}, at=100)
        self.save("sweep", self.SEEN, {"ws:a": self.e("LATER", at)}, at=200)
        self.assertEqual(self.restored()["ws:a"]["sig"], "LATER")
        shutil.rmtree(self.src)                                     # same result whichever folder name sorts first
        self.save("sweep", self.SEEN, {"ws:a": self.e("FIRST", at)}, at=100)
        self.save("foodbanks", self.SEEN, {"ws:a": self.e("LATER", at)}, at=200)
        self.assertEqual(self.restored()["ws:a"]["sig"], "LATER")

    def test_unknown_prefix_keys_have_no_owner_and_newest_reading_wins(self):
        """A key no layer owns is never deleted by any layer's save: the newest reading of it is kept."""
        older = self.e("A", "2026-01-04T04:41:00+00:00"); newer = self.e("B", "2026-01-05T04:41:00+00:00")
        self.save("foodbanks", self.SEEN, {"zz:a": newer, "fb:x": older}, at=100)
        self.save("shelters", self.SEEN, {"zz:a": older}, at=200)
        self.save("warmspaces", self.SEEN, {}, at=300)
        self.assertEqual(self.restored(), {"fb:x": older, "zz:a": newer})

    def test_merged_map_is_written_like_the_gate_writes_it(self):
        """Same bytes as discover's own dump, so an unchanged map is not seen as changed by the save step."""
        import json
        a = self.e("A", "2026-01-05T04:41:00+00:00"); x = self.e("X", "2026-01-05T04:29:00+00:00")
        self.save("shelters", self.SEEN, {"sh:a": a}, at=100)
        self.save("foodbanks", self.SEEN, {"fb:x": x}, at=200)
        dst = os.path.join(self.d, "fmt"); os.makedirs(dst); self.m.restore(self.src, dst)
        want = os.path.join(self.d, "want.json")
        json.dump({"sh:a": a, "fb:x": x}, open(want, "w"), indent=0, sort_keys=True, ensure_ascii=False)
        self.assertEqual(open(os.path.join(dst, self.SEEN), "rb").read(), open(want, "rb").read())
        gate = open(os.path.join(ROOT, "scripts", "discover.py"), encoding="utf-8").read()
        self.assertIn("json.dump(new_seen, open(os.path.join(R, XC_SEEN), \"w\"), indent=0, sort_keys=True, ensure_ascii=False)", gate)

    def test_checkout_copy_still_wins(self):
        self.save("shelters", self.SEEN, {"sh:a": self.e("A", "2026-01-05T04:41:00+00:00")})
        dst = os.path.join(self.d, "co"); os.makedirs(os.path.join(dst, "logs"))
        open(os.path.join(dst, self.SEEN), "w").write("{}")
        self.assertEqual(self.restored(dst=dst), {})

    def test_other_shared_files_still_newest_save(self):
        self.save("foodbanks", "reports/learning_state.json", "old", at=100)
        self.save("sweep", "reports/learning_state.json", "new", at=200)
        dst = os.path.join(self.d, "ls"); os.makedirs(dst); self.m.restore(self.src, dst)
        self.assertEqual(open(os.path.join(dst, "reports", "learning_state.json")).read(), "new")

    def test_restored_reading_confirms_the_next_identical_read(self):
        """A shelter reading restored after a later food bank save still counts as the first read on the next shelter
        run, and the same run's reading never counts twice: discover's gate compares sig, page and run time."""
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import discover
        gate = open(os.path.join(ROOT, "scripts", "discover.py"), encoding="utf-8").read()
        self.assertIn('if not sig or prev.get("sig") != sig or prev.get("source_url") != src or prev.get("run_at") == run_at:', gate)
        sig = discover._tsig({"mon": [["10:00", "12:00"]]}); url = "https://example.org/times"
        first = self.e(sig, "2026-01-05T04:41:00+00:00", url)
        self.save("shelters", self.SEEN, {"sh:a": first}, at=100)
        self.save("foodbanks", self.SEEN, {"fb:x": self.e("X", "2026-01-05T04:29:00+00:00")}, at=200)
        prev = self.restored()["sh:a"]
        confirms = lambda run_at, s=sig, u=url: not (not s or prev.get("sig") != s or prev.get("source_url") != u or prev.get("run_at") == run_at)
        self.assertTrue(confirms("2026-01-05T12:41:00+00:00"))            # next run, identical read: confirmed
        self.assertFalse(confirms("2026-01-05T04:41:00+00:00"))           # same run: never counts twice
        self.assertFalse(confirms("2026-01-05T12:41:00+00:00", s=discover._tsig({"mon": [["10:00", "13:00"]]})))

    def test_round_trip_through_the_script(self):
        import json
        remote = os.path.join(self.d, "p.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
        seed = os.path.join(self.d, "seed"); subprocess.run(["git", "clone", "-q", remote, seed], check=True)
        open(os.path.join(seed, "README.md"), "w").write("v\n")
        g = ["git", "-C", seed, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(g + ["add", "."], check=True); subprocess.run(g + ["commit", "-qm", "s"], check=True)
        subprocess.run(g + ["push", "-q", "origin", "HEAD:main"], check=True)
        def run(cwd, *a):
            env = dict(os.environ, PRIVATE_STATE_REPO="file://" + remote, HELPMAP_STATE_KEY="k", GITHUB_REF="refs/heads/main",
                       PRIVATE_STATE_RETRY_WAIT="0", GITHUB_ENV=os.path.join(self.d, "genv"),
                       PRIVATE_STATE_WORK=os.path.join(self.d, "w-" + os.path.basename(cwd)))
            return subprocess.run(["bash", SCRIPT, *a], cwd=cwd, env=env, capture_output=True, text=True)
        runs = {}
        for layer, key in (("warmspaces", "ws:t"), ("shelters", "sh:t"), ("foodbanks", "fb:t")):
            c = os.path.join(self.d, layer); os.makedirs(c); run(c, "restore"); runs[layer] = (c, key)
        import time
        for layer, (c, key) in runs.items():      # parallel runs: each restored nothing, each saves only its own kind
            os.makedirs(os.path.join(c, "logs"), exist_ok=True)
            json.dump({key: self.e("S-" + layer, "2026-01-05T05:00:00+00:00")}, open(os.path.join(c, self.SEEN), "w"))
            self.assertIn("saved", run(c, "save", layer).stdout); time.sleep(1.1)
        nxt = os.path.join(self.d, "next"); os.makedirs(nxt); r = run(nxt, "restore")
        got = json.load(open(os.path.join(nxt, self.SEEN)))
        self.assertEqual(sorted(got), ["fb:t", "sh:t", "ws:t"], r.stdout + r.stderr)
        self.assertEqual(got["sh:t"]["sig"], "S-shelters")
        self.assertNotIn("S-shelters", r.stdout + r.stderr)


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
                    run = s.get("run", "")
                    is_tests = bool(re.search(r"-m (unittest|pytest)\b", run))
                    env = s.get("env") or {}
                    # only the test-suite steps switch the check off, so the suite never depends on run state
                    if is_tests: self.assertEqual(str(env.get("HELPMAP_STATE_CHECK")), "0", (name, s.get("name")))
                    else: self.assertNotIn("HELPMAP_STATE_CHECK", env, (name, s.get("name")))
                    self.assertNotIn("HELPMAP_STATE_RESTORED", str(env), name)
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
