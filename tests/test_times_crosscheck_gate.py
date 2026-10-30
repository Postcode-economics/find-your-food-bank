"""Dean 27 Oct 2026 (vault rule 33) on the REGULAR REFRESH path (discover.cross_check_times): a changed time goes on the map
only when the postcode is matched, identical times are read on 2 separate runs, the source is the org's own site, nothing
conflicts, and it is not known times -> closed/empty. Every change is logged with an undo; everything else is held in
reports/pending_dean.md with the old times kept. Each safeguard is proven to block on its own."""
import os, sys, json, hashlib, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D, times_revert as R
R1, R2 = "2026-10-27T03:00:00+00:00", "2026-10-27T11:00:00+00:00"
ON, OFF = {"times_auto_apply": True}, {"times_auto_apply": False}
FILL = " lorem ipsum" * 40
OLD = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}, "raw": "Tuesday 10am - 12pm"}
NEW_ST = {"thu": [["14:00", "16:00"]]}
def html(times="Thursday 2pm - 4pm", pc="AB1 2CD"):
    return "<html><body><h1>Riverside Food Bank</h1><p>Emergency food parcels. Riverside Hall, 1 High St, %s. %s.</p>%s</body></html>" % (pc, times, FILL)
def pg(h, final="https://x.org/"):
    return {"http": 200, "final_url": final, "html": h, "etag": "e", "last_modified": "", "sha256": hashlib.sha256(h.encode()).hexdigest()}
def fetch(site_map):
    def f(u):
        for k, v in site_map.items():
            if u.rstrip("/") == k.rstrip("/"): return v
        return {"http": 404, "final_url": u, "html": ""}
    return f
def item(**kw): return dict({"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(OLD)}, **kw)
class Gate(unittest.TestCase):
    def setUp(self): self.root = tempfile.mkdtemp()
    def run1(self, it, f, run_at, rules=ON, kind="fb", field="opening_times", root="default"):
        return D.cross_check_times(it, kind, field, f, state_root=self.root if root == "default" else root, rules=rules, run_at=run_at)
    def twice(self, f1, f2=None, it=None, rules=ON, **kw):
        it = it or [item()]
        self.run1([dict(x) for x in it], f1, R1, rules, **kw); return it, self.run1(it, f2 or f1, R2, rules, **kw)
    def held(self, log, it, text, field="opening_times", old=OLD):
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertTrue(any(text in w for w in log["a"]["held"]), log["a"]["held"])
        self.assertEqual(it[0][field], old)   # old times kept
        md = open(os.path.join(self.root, "reports", "pending_dean.md")).read(); self.assertIn("`a`", md); self.assertIn(text, md)
        al = os.path.join(self.root, "reports", "times_auto_applied.json")
        self.assertFalse(os.path.exists(al) and json.load(open(al)))
    # ---- positive: logged with an undo ----
    def test_positive_applied_logged_and_undoable(self):
        it, log = self.twice(fetch({"https://x.org/": pg(html())}))
        self.assertEqual(log["a"]["status"], "changed"); self.assertTrue(log["a"]["auto_applied"])
        self.assertEqual(it[0]["opening_times"]["structured"], NEW_ST); self.assertEqual(it[0]["times_status"], "updated")
        rec = json.load(open(os.path.join(self.root, "reports", "times_auto_applied.json")))[0]
        self.assertEqual((rec["id"], rec["kind"], rec["path"], rec["old"], rec["first_run_at"], rec["second_run_at"]), ("a", "fb", "cross_check", OLD, R1, R2))
        self.assertEqual(rec["revert"], "python scripts/times_revert.py fb:a")
        self.assertIn("AUTO-APPLIED `a`", open(os.path.join(self.root, "reports", "pending_dean.md")).read())
        R.revert("fb:a", root=self.root)
        self.assertTrue(json.load(open(os.path.join(self.root, "reports", "times_auto_applied.json")))[0]["reverted"])
        it3 = [item()]; l3 = self.run1(it3, fetch({"https://x.org/": pg(html())}), "2026-10-27T19:00:00+00:00")   # undone: never re-applied
        self.assertEqual(l3["a"]["status"], "held_for_dean"); self.assertIn("undone by Dean", l3["a"]["reason"]); self.assertEqual(it3[0]["opening_times"], OLD)
    def test_hand_set_same_table_held_new_table_applies(self):
        stored = dict(OLD, reader="hand-set 2026-10-24 (Dean; church calendar, temporary venue)", protected=True)
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), it=[item(opening_times=stored)])
        self.assertEqual(log["a"]["status"], "changed")
        self.assertTrue(log["a"].get("auto_applied"))
        self.assertEqual(it[0]["opening_times"]["structured"], NEW_ST)
        self.assertTrue(os.path.exists(os.path.join(self.root, "reports", "times_auto_applied.json")))

    def test_hand_set_same_table_on_two_runs_is_held(self):
        stored = dict(OLD, reader="hand-set 2026-10-24 (Dean; church calendar, temporary venue)", protected=True)
        it, log = self.twice(fetch({"https://x.org/": pg(html("Tuesday 10am - 12pm"))}), it=[item(opening_times=stored)])
        self.assertEqual(log["a"]["status"], "confirmed")
        self.assertEqual(it[0]["opening_times"]["structured"], OLD["structured"])

    def test_hand_reviewed_marker_inside_the_reader_is_kept(self):
        stored = dict(OLD, reader="sa_corps_page (hand-reviewed)", protected=True)
        os.makedirs(os.path.join(self.root, "overrides"), exist_ok=True)
        json.dump({"a": stored}, open(os.path.join(self.root, "overrides", "opening_times.json"), "w"))
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), it=[item(opening_times=stored)])
        self.assertEqual(log["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], NEW_ST)
        self.assertIn("hand-reviewed", it[0]["opening_times"]["reader"])

    def test_shelter_hours_positive(self):
        it = [item(id="a", opening_times=None, hours={"Tue": "10:00 - 12:00"})]; it[0].pop("opening_times")
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), it=it, kind="sh", field="hours")
        self.assertEqual(it[0]["hours"], {"Thu": "14:00 - 16:00"})
    # ---- each safeguard blocks on its own ----
    def test_first_run_alone_is_held(self):
        it = [item()]; log = self.run1(it, fetch({"https://x.org/": pg(html())}), R1); self.held(log, it, "2 separate runs")
    def test_two_runs_with_different_times_held(self):
        it, log = self.twice(fetch({"https://x.org/": pg(html("Friday 9am - 11am"))}), fetch({"https://x.org/": pg(html())})); self.held(log, it, "2 separate runs")
    def test_same_run_twice_is_not_two_runs(self):
        f = fetch({"https://x.org/": pg(html())}); self.run1([item()], f, R1); it = [item()]; log = self.run1(it, f, R1); self.held(log, it, "2 separate runs")
    def test_no_saved_state_never_applies(self):
        f = fetch({"https://x.org/": pg(html())}); it = [item()]
        D.cross_check_times([item()], "fb", "opening_times", f, rules=ON, run_at=R1); log = D.cross_check_times(it, "fb", "opening_times", f, rules=ON, run_at=R2)
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertEqual(it[0]["opening_times"], OLD)
    def test_postcode_not_matched_held(self):
        g = D.times_gate_reasons(item(), "fb", "opening_times", {"structured": NEW_ST, "status": "TIMES_FOUND"}, [html(pc="ZZ9 9ZZ")],
                                 {"final_url": "https://x.org/"}, {"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}}, {}, True, R2)
        self.assertEqual(len(g), 1, g); self.assertIn("postcode not matched", g[0])
        it, log = self.twice(fetch({"https://x.org/": pg(html(pc="ZZ9 9ZZ"))}))   # end to end: never applied
        self.assertNotEqual(log["a"]["status"], "changed"); self.assertEqual(it[0]["opening_times"], OLD)
    def test_item_without_postcode_held(self):
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), it=[item(postcode="")])
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertIn("postcode not matched", log["a"]["reason"])
    def test_not_own_site_held(self):
        g = D.times_gate_reasons(item(), "fb", "opening_times", {"structured": NEW_ST, "status": "TIMES_FOUND"}, [html()],
                                 {"final_url": "https://directory.example.com/x"}, {"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://directory.example.com/x", "run_at": R1}}, {}, True, R2)
        self.assertEqual(len(g), 1, g); self.assertIn("own site", g[0])
    def test_conflicting_own_pages_held(self):
        g = D.times_gate_reasons(item(), "fb", "opening_times", {"structured": NEW_ST, "status": "TIMES_FOUND"}, [html(), html("Monday 9am - 10am")],
                                 {"final_url": "https://x.org/"}, {"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}}, {}, True, R2)
        self.assertEqual(len(g), 1, g); self.assertIn("conflict", g[0])
    def test_known_to_closed_or_empty_held(self):
        for new in ({"status": "CLOSED", "structured": None}, {"status": "TIMES_FOUND", "structured": {"wed": []}}, None):
            g = D.times_gate_reasons(item(), "fb", "opening_times", new, [html()], {"final_url": "https://x.org/"},
                                     {"fb:a": {"sig": None, "source_url": "https://x.org/", "run_at": R1}}, {}, True, R2)
            self.assertTrue(any("closed/empty" in w for w in g), g)
    def test_off_holds(self):
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), rules=OFF); self.held(log, it, "auto-apply is off")
    def test_branch_copy_held_after_two_runs(self):
        it = [item(), item(id="b")]
        it, log = self.twice(fetch({"https://x.org/": pg(html())}), it=it)
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertIn("several branches", log["a"]["reason"]); self.assertEqual(it[0]["opening_times"], OLD)
    def test_hand_checked_same_table_held_not_blanked(self):
        prot = dict(OLD, reader="hand-reviewed 2026-10-23", protected=True)
        it, log = self.twice(fetch({"https://x.org/": pg(html("Tuesday 10am - 12pm"))}), it=[item(opening_times=dict(prot))])
        self.assertEqual(log["a"]["status"], "confirmed")
        self.assertEqual(it[0]["opening_times"]["structured"], OLD["structured"])
    def test_a_later_pass_keeps_another_places_seen_row(self):
        """Centres checked after the main pass must not wipe the rows the main pass just stored."""
        f = fetch({"https://x.org/": pg(html())})
        self.run1([item()], f, R1)
        other = [item(id="b", website="https://y.org/")]
        self.run1(other, fetch({}), "2026-10-27T04:00:00+00:00")
        seen = json.load(open(os.path.join(self.root, "logs", "times_crosscheck_seen.json")))
        self.assertEqual(seen["fb:a"]["run_at"], R1)
        self.assertNotIn("fb:b", seen)
    def test_refresh_scripts_pass_saved_state(self):
        here = os.path.join(os.path.dirname(__file__), "..", "scripts")
        for f in ("build.py", "build_shelters.py", "build_warmspaces.py"):
            src = open(os.path.join(here, f)).read(); i = src.index("discover.cross_check_times(")
            self.assertIn("state_root=", src[i:src.index("\n", i)], f)
    def test_nothing_found_keeps_listing_and_writes_no_pending_row(self):
        """Dean 27 Oct 2026 12:12 GMT: nothing read means no change, no blank, no closed, and no pending row."""
        os.makedirs(os.path.join(self.root, "reports"))
        pd = os.path.join(self.root, "reports", "pending_dean.md")
        open(pd, "w").write("# Pending for Dean\n\n<!-- times crosscheck fb -->\nNothing pending.\n<!-- /times crosscheck fb -->\n\n<!-- closures -->\nkeep me\n<!-- /closures -->\n")
        it = [item(phone="01111 111111", tel="01111 111111")]
        stored = json.loads(json.dumps(it[0]["opening_times"]))
        page = "<html><body><p>Riverside Food Bank, AB1 2CD. Please call before you come. Telephone 09999 999999.</p>%s</body></html>" % FILL
        log = self.run1(it, fetch({"https://x.org/": pg(page)}), R1)
        self.assertEqual(log["a"]["status"], "unconfirmed")
        self.assertEqual(it[0]["opening_times"], stored)
        self.assertEqual((it[0]["phone"], it[0]["tel"]), ("01111 111111", "01111 111111"))
        self.assertNotIn("closed", json.dumps(it[0]["opening_times"]).lower())
        md = open(pd).read()
        self.assertNotIn("Nothing pending", md); self.assertNotIn("`a`", md); self.assertNotIn("times crosscheck", md)
        self.assertIn("keep me", md)
        gone = [item()]
        self.run1(gone, fetch({}), R2)
        self.assertEqual(gone[0]["opening_times"], OLD)
        self.assertNotIn("Nothing pending", open(pd).read())
    def test_unread_candidate_does_not_change_the_listing(self):
        it = item(phone="01111 111111", tel="01111 111111")
        before = json.loads(json.dumps(it))
        rec = {"site": "https://x.org/", "status": "changed"}
        D.times_gate_apply([(it, rec, None, ["AB1 2CD no times here"], {"final_url": "https://x.org/"})],
                           "fb", "opening_times", "2026-10-27", {}, self.root, ON, R2, keep_ids=["a"])
        self.assertEqual(it, before)
        self.assertFalse(os.path.exists(os.path.join(self.root, "reports", "pending_dean.md")))
    def test_explicit_closed_reading_is_still_held(self):
        """A real closed table is still held. Only a failed read is silent."""
        it = item()
        rec = {"site": "https://x.org/"}
        new = {"status": "CLOSED", "structured": None, "raw": "Closed"}
        D.times_gate_apply([(it, rec, new, [html()], {"final_url": "https://x.org/"})],
                           "fb", "opening_times", "2026-10-27", {}, self.root, ON, R2, keep_ids=["a"])
        self.assertEqual(it["opening_times"], OLD)
        md = open(os.path.join(self.root, "reports", "pending_dean.md")).read()
        self.assertIn("`a`", md); self.assertIn("closed/empty", md)
    def test_phone_mismatch_is_not_an_hours_conflict_and_phone_stays_held(self):
        """Dean 27 Oct 2026 12:13 GMT: only a second, different hours table is a source conflict. The phone fix stays held."""
        it = [item(phone="01111 111111", tel="01111 111111")]
        it, log = self.twice(fetch({"https://x.org/": pg(html(times="Thursday 2pm - 4pm. Telephone 09999 999999"))}), it=it)
        self.assertTrue(log["a"].get("auto_applied")); self.assertEqual(it[0]["opening_times"]["structured"], NEW_ST)
        self.assertEqual((it[0]["phone"], it[0]["tel"]), ("01111 111111", "01111 111111"))
        self.assertNotIn("phone", (log["a"].get("reason") or "").lower())
        rec = json.load(open(os.path.join(self.root, "reports", "times_auto_applied.json")))[0]
        self.assertEqual(rec["old"], OLD); self.assertNotIn("09999", json.dumps(rec["new"]))
        phones = " Telephone 09999 999999."
        g = D.times_gate_reasons(item(phone="01111 111111", tel="01111 111111"), "fb", "opening_times",
                                 {"structured": NEW_ST, "status": "TIMES_FOUND", "raw": "Thursday 2pm - 4pm"},
                                 [html() + phones, html("Monday 9am - 10am") + phones],
                                 {"final_url": "https://x.org/"},
                                 {"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}},
                                 {}, True, R2)
        self.assertEqual(g, ["conflict: own-site pages give different times"])
        here = os.path.join(os.path.dirname(__file__), "..", "scripts")
        gate = open(os.path.join(here, "discover.py")).read()
        gate = gate[gate.index("def times_gate_reasons"):gate.index("def cross_check_times")]
        finder = open(os.path.join(here, "times_finder.py")).read()
        finder = finder[finder.index("def strict_checks"):finder.index("def decide")]
        for src in (gate, finder):
            self.assertNotIn("confidence_for", src)
            self.assertNotIn("allow_under_rules", src)
            self.assertNotIn("conflicts(", src)
    def test_late_pass_that_finds_nothing_keeps_the_earlier_hold(self):
        f = fetch({"https://x.org/": pg(html())})
        it = [item()]; log = self.run1(it, f, R1)
        pd = os.path.join(self.root, "reports", "pending_dean.md")
        self.assertIn("`a`", open(pd).read())
        b = item(id="b", type="foodbank", website="https://y.org/", phone="01111 111111")
        stored = json.loads(json.dumps(b["opening_times"]))
        late = D.check_missing([it[0], b], log, "fb", "opening_times", fetcher=fetch({}), state_root=self.root, rules=ON, run_at=R2)
        self.assertEqual(late, ["b"])
        self.assertEqual(b["opening_times"], stored); self.assertEqual(b["phone"], "01111 111111")
        md = open(pd).read()
        self.assertIn("`a`", md); self.assertNotIn("`b`", md); self.assertNotIn("Nothing pending", md)
    def test_all_closed_reading_is_held_and_known_times_stay(self):
        it = item(); new = {"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "17:00"]]}, "all_closed": True, "raw": "Closed"}
        D.times_gate_apply([(it, {"site": "https://x.org/"}, new, [html()], {"final_url": "https://x.org/"})],
                           "fb", "opening_times", "2026-10-27", {}, self.root, ON, R2, keep_ids=["a"])
        g = D.times_gate_reasons(item(), "fb", "opening_times", new, [html()], {"final_url": "https://x.org/"},
                                 {"fb:a": {"sig": json.dumps(new["structured"], sort_keys=True), "source_url": "https://x.org/", "run_at": R1}}, {}, True, R2)
        self.assertEqual(g, ["would change known times to closed/empty"])
        self.assertEqual(it["opening_times"], OLD)
        self.assertNotIn("all_closed", it["opening_times"])
    def test_one_hours_apply_path(self):
        """The refresh writes hours only through the strict gate. No second writer, and no one-run fallback."""
        here = os.path.join(os.path.dirname(__file__), "..", "scripts")
        src = open(os.path.join(here, "discover.py")).read()
        self.assertNotIn("def client_week", src)
        self.assertNotIn("seen_once", src)
        window = src[src.index('elif st == "changed":'):src.index('elif st == "unconfirmed"')]
        self.assertNotIn("i[field] =", window)
        self.assertIn("cands.append", window)
        build = open(os.path.join(here, "build.py")).read()
        call = build[build.index("discover.cross_check_times("):build.index("\n", build.index("discover.cross_check_times("))]
        self.assertIn("state_root=ROOT", call)
        self.assertNotIn("seen=", call)
    def test_pending_section_kept_by_publish_gate(self):
        s = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "publish_gate.py")).read()
        for k in ("fb", "sh", "ws"): self.assertIn("'times crosscheck %s'" % k, s)
if __name__ == "__main__": unittest.main()
