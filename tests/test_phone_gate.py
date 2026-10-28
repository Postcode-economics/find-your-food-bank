"""Dean, 28 Oct 2026: a clear single new phone on the organisation's own site may auto-apply, but only through the same
strict gate as times: read on the organisation's OWN host, identical on 2 separate runs, no conflicting own-site number,
and every change logged once with its source URL and an undo command. Anything else is held. Each rule blocks on its own."""
import json, os, re, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import full_check as F
import phone_revert

U = "https://www.riverside-fb.org.uk/"
R1, R2 = "2026-10-27T03:29:00+00:00", "2026-10-27T11:29:00+00:00"
NEW = "01234567890"
def res(**kw):
    return dict({"phones": [NEW], "tel": [NEW], "final_url": U, "pages": [U, U + "contact/"], "checked_at": R2}, **kw)
def prev(**kw):
    return dict({"phones": [NEW], "tel": [NEW], "final_url": U, "checked_at": R1}, **kw)


class Gate(unittest.TestCase):
    def test_clear_own_site_number_on_two_runs_passes(self):
        self.assertEqual(F.phone_gate_reasons(U, res(), prev()), [])
        self.assertEqual(F.phone_gate_reasons(U, res(final_url="https://riverside-fb.org.uk/home"), prev()), [])   # www. is the same host
        self.assertEqual(F.phone_gate_reasons(U, res(pages=["https://help.riverside-fb.org.uk/"]), prev()), [])  # own subdomain

    def only(self, why, text):
        self.assertEqual(len(why), 1, why); self.assertIn(text, why[0])

    def test_off_host_final_url_is_held(self):
        self.only(F.phone_gate_reasons(U, res(final_url="https://www.kent.gov.uk/contact"), prev()), "own host")

    def test_an_off_host_page_is_held(self):
        self.only(F.phone_gate_reasons(U, res(pages=[U, "https://www.facebook.com/riverside"]), prev()), "own host")

    def test_lookalike_host_is_not_own(self):
        self.assertFalse(F.own_host(U, "https://riverside-fb.org.uk.evil.example/"))
        self.assertFalse(F.own_host(U, "https://notriverside-fb.org.uk/"))
        self.assertFalse(F.own_host(U, ""))

    def test_a_second_own_site_number_conflicts(self):
        self.only(F.phone_gate_reasons(U, res(phones=[NEW, "01234000000"]), prev(phones=[NEW, "01234000000"])), "exactly one")

    def test_number_that_is_not_clickable_is_held(self):
        self.only(F.phone_gate_reasons(U, res(tel=[]), prev()), "exactly one")

    def test_first_sight_is_held(self):
        self.only(F.phone_gate_reasons(U, res(), {}), "2 separate runs")

    def test_different_number_last_run_is_held(self):
        self.only(F.phone_gate_reasons(U, res(), prev(phones=["01234111111"])), "2 separate runs")

    def test_same_run_twice_is_not_two_runs(self):
        self.only(F.phone_gate_reasons(U, res(), prev(checked_at=R2)), "2 separate runs")

    def test_last_run_off_host_does_not_count(self):
        self.only(F.phone_gate_reasons(U, res(), prev(final_url="https://www.kent.gov.uk/")), "2 separate runs")

    def test_number_dean_undid_is_never_reapplied(self):
        self.only(F.phone_gate_reasons(U, res(), prev(), {U: NEW}), "undone by Dean")
        self.assertEqual(F.phone_gate_reasons(U, res(), prev(), {U: "01234999999"}), [])


class UndoLog(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "reports"))
        self.log = os.path.join(self.d, "reports", "phone_auto_applied.json")
        self.fix = dict(old="01234000000", new=NEW, since="2026-10-27", source=U + "contact/", label="", first_run_at=R1, second_run_at=R2)

    def test_logged_once_with_source_and_undo(self):
        self.assertEqual(len(F.log_phone_changes([(U, self.fix)], self.log)), 1)
        for _ in range(3):   # build.py rebuilds from the feed, so the same fix is written again every run
            self.assertEqual(F.log_phone_changes([(U, self.fix)], self.log), [])
        rec, = json.load(open(self.log))
        self.assertEqual((rec["website"], rec["old"], rec["new"], rec["source_url"], rec["first_run_at"], rec["second_run_at"]),
                         (U, "01234000000", NEW, U + "contact/", R1, R2))
        self.assertEqual(rec["revert"], "python scripts/phone_revert.py " + U)

    def test_revert_removes_the_fix_and_blocks_the_number(self):
        json.dump({U: self.fix, "https://other.org/": dict(self.fix, new="01234222222")}, open(os.path.join(self.d, "reports", "phone_fixes.json"), "w"))
        F.log_phone_changes([(U, self.fix)], self.log)
        phone_revert.revert(U, root=self.d)
        self.assertTrue(json.load(open(self.log))[0]["reverted"])
        fixes = json.load(open(os.path.join(self.d, "reports", "phone_fixes.json")))
        self.assertNotIn(U, fixes); self.assertIn("https://other.org/", fixes)
        undone = json.load(open(os.path.join(self.d, "overrides", "phone_auto_undone.json")))
        self.assertEqual(undone, {U: NEW})
        self.only_undone = F.phone_gate_reasons(U, res(), prev(), undone)
        self.assertTrue(any("undone by Dean" in w for w in self.only_undone))
        F.log_phone_changes([(U, self.fix)], self.log)   # a later re-apply after the revert is a new entry, not hidden
        self.assertEqual(len(json.load(open(self.log))), 2)
        with self.assertRaises(SystemExit):
            phone_revert.revert("https://never-logged.org/", root=self.d)


class Wiring(unittest.TestCase):
    """The gate sits in full_check.main() on the only path that writes a new phone fix."""
    src = open(os.path.join(ROOT, "scripts", "full_check.py"), encoding="utf-8").read()
    main = src[src.index("def main():"):]

    def test_gate_runs_before_a_fix_is_recorded(self):
        g = self.main.index("gate = phone_gate_reasons(u, r, prev, undone) if clear else []")
        held = self.main.index("elif clear and gate:")
        rec = self.main.index("fixes[u] = dict(old=old, new=new")
        self.assertLess(g, held); self.assertLess(held, rec)
        self.assertIn("'phone fix held (strict gate)'", self.main)
        self.assertIn("allow_under_rules('clear single new phone on own site'", self.main)
        self.assertEqual(len(re.findall(r"fixes\[u\] = ", self.main)), 1)

    def test_undone_fixes_are_dropped_and_every_write_is_logged(self):
        self.assertIn("fixes = {u: f for u, f in fixes.items() if undone.get(u) != f.get('new')}", self.main)
        a = self.main.index("apply_phone_fixes(by_site, fixes, flag, ROOT, applied=applied_phones)")
        self.assertIn("log_phone_changes(applied_phones)", self.main[a:a + 300])

    def test_undo_log_is_published_and_merge_safe(self):
        wf = open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
        self.assertRegex(wf, r"git_add_existing\.sh [^\n]* reports/ ")
        attrs = open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8").read()
        self.assertIn("reports/phone_auto_applied.json -merge", attrs)
        self.assertIn("overrides/phone_auto_undone.json -merge", attrs)
        self.assertEqual(json.load(open(os.path.join(ROOT, "reports", "phone_auto_applied.json"))), [])


if __name__ == "__main__":
    unittest.main()
