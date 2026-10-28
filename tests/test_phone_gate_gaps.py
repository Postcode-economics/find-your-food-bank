"""Gaps in the strict phone auto-apply: sticky undo for every undone number, clickable on both runs, and the gate
as main() actually runs it (applied / held / undone in one run)."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import full_check as F, phone_revert

U = "https://www.riverside-fb.org.uk/"
R1, R2 = "2026-10-27T03:29:00+00:00", "2026-10-27T11:29:00+00:00"
def res(n, **kw): return dict({"phones": [n], "tel": [n], "final_url": U, "pages": [U], "checked_at": R2}, **kw)
def prev(n, **kw): return dict({"phones": [n], "tel": [n], "final_url": U, "checked_at": R1}, **kw)


class Undo(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.d, True); os.makedirs(os.path.join(self.d, "reports"))
        self.log = os.path.join(self.d, "reports", "phone_auto_applied.json")

    def test_every_number_dean_undid_stays_blocked(self):
        for n in ("01234500001", "01234500002"):
            f = dict(old="01234000000", new=n, source=U, first_run_at=R1, second_run_at=R2)
            json.dump({U: f}, open(os.path.join(self.d, "reports", "phone_fixes.json"), "w"))
            F.log_phone_changes([(U, f)], self.log); phone_revert.revert(U, root=self.d)
        undone = json.load(open(os.path.join(self.d, "overrides", "phone_auto_undone.json")))
        for n in ("01234500001", "01234500002"):
            self.assertTrue(any("undone by Dean" in w for w in F.phone_gate_reasons(U, res(n), prev(n), undone)), n)

    def test_revert_leaves_a_newer_fix_alone(self):
        old = dict(old="01234000000", new="01234500001", source=U)
        F.log_phone_changes([(U, old)], self.log)
        newer = dict(old="01234000000", new="01234500009", source=U)
        json.dump({U: newer}, open(os.path.join(self.d, "reports", "phone_fixes.json"), "w"))
        phone_revert.revert(U, root=self.d)
        self.assertEqual(json.load(open(os.path.join(self.d, "reports", "phone_fixes.json"))), {U: newer})


class MainPath(unittest.TestCase):
    """One run, three sites: clear on 2 runs (applied), last run read off-host (held, strict gate), Dean undid it (held)."""
    def test_main_applies_holds_and_honours_undo(self):
        a, b, c = "https://a-fb.example/", "https://b-fb.example/", "https://c-fb.example/"
        new = ["02000000000"]
        items = [dict(id="gap-" + k, type="foodbank", name=k, foodbank=k, website=u, phone="01000000000", tel="01000000000")
                 for k, u in (("a", a), ("b", b), ("c", c))]
        last = lambda u, fin=None: {"phones": new, "tel": new, "final_url": fin or u + "contact", "checked_at": R1, "access": "unclear"}
        store = {"full_check_state.json": {"sites": {a: last(a), b: last(b, "https://www.facebook.com/b"), c: last(c)}, "ids": [i["id"] for i in items]}}
        root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, "overrides"))
        json.dump({c: new[0]}, open(os.path.join(root, "overrides", "phone_auto_undone.json"), "w"))
        json.dump({"listings": {}}, open(os.path.join(root, "overrides", "phone_baseline.json"), "w"))   # no baseline file locks every listing
        written = {}; rep = tempfile.mkdtemp()
        def fake(u):
            return dict(url=u, ok=True, final_url=u + "contact", pages=[u + "contact"], access="unclear", hours_hash="", hours_sample=[],
                        seasonal=None, closed=None, perm_closed=None, phones=new, tel=new, needs=None, checked_at=R2, http=200)
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.ROOT)
        F.rj = lambda n, d: store.get(n, d); F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ("x=", {"items": items}); F.load_access = lambda: {}
        F.write_md = lambda *x: None; F.REP = rep; F.check_site = fake; F.ROOT = root
        os.environ["DRY_RUN"] = "1"
        try: F.main()
        finally:
            (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.ROOT) = orig; os.environ.pop("DRY_RUN", None)
        fixes = written["phone_fixes.json"]
        self.assertEqual(set(fixes), {a})
        self.assertEqual((fixes[a]["first_run_at"], fixes[a]["second_run_at"], fixes[a]["source"]), (R1, R2, a + "contact"))
        self.assertEqual([i["phone"] for i in items], ["02000000000", "01000000000", "01000000000"])
        cats = {v["website"]: (v["category"], v.get("note", "")) for v in written["daily_review.json"][F.DAY]["items"].values() if v.get("website") in (b, c)}
        self.assertEqual(cats[b][0], "phone fix held (strict gate)"); self.assertIn("2 separate runs", cats[b][1])
        self.assertEqual(cats[c][0], "phone fix held (strict gate)"); self.assertIn("undone by Dean", cats[c][1])


if __name__ == "__main__": unittest.main()
