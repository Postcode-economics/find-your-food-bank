"""Intelligent-mode safety rails. The switch stays off; these tests turn it on only inside a temp root."""
import hashlib, io, json, os, shutil, sys, tempfile, unittest
from contextlib import redirect_stdout
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
FIX = os.path.join(HERE, "fixtures", "intelligent_rails")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D
import intelligent_rails as IR
import times_finder as TF

R1, R2 = "2026-10-27T03:00:00+00:00", "2026-10-27T11:00:00+00:00"
FILL = " lorem ipsum" * 40
OLD = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]]}, "raw": "Tuesday 10am - 12pm"}
NEW_ST = {"thu": [["14:00", "16:00"]]}
ON = {"times_auto_apply": True}
IM = {"times_auto_apply": True, "intelligent_mode": True}


def html(times="Thursday 2pm - 4pm", pc="AB1 2CD"):
    return "<html><body><h1>Riverside Food Bank</h1><p>Emergency food parcels. Riverside Hall, 1 High St, %s. %s.</p>%s</body></html>" % (pc, times, FILL)


def pg(h, final="https://x.org/", **kw):
    out = {"http": 200, "final_url": final, "html": h, "etag": "e", "last_modified": "", "sha256": hashlib.sha256(h.encode()).hexdigest()}
    out.update(kw)
    return out


def fetch(site_map):
    def f(u):
        for k, v in site_map.items():
            if u.rstrip("/") == k.rstrip("/"):
                return v
        return {"http": 404, "final_url": u, "html": ""}
    return f


def item(**kw):
    base = {"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": dict(OLD)}
    base.update(kw)
    return base


def _js(path, marker):
    raw = open(path, encoding="utf-8").read()
    return json.loads(raw[raw.index(marker) + len(marker): raw.rindex("}") + 1])


class Rails(unittest.TestCase):
    def setUp(self):
        IR.reset()
        self.root = tempfile.mkdtemp()
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        IR.reset()

    def twice(self, rules, root=None):
        root = root or self.root
        f = fetch({"https://x.org/": pg(html())})
        it = [item()]
        D.cross_check_times([dict(x) for x in it], "fb", "opening_times", f, state_root=root, rules=rules, run_at=R1)
        log = D.cross_check_times(it, "fb", "opening_times", f, state_root=root, rules=rules, run_at=R2)
        return it, log

    def test_coverage_numbers_from_today(self):
        self.assertTrue(IR.coverage_reasons({"source_pages": 1685, "source_opened": 598}))
        self.assertTrue(IR.coverage_reasons({"budget_skipped": 98}))
        self.assertTrue(any("no time" in r for r in IR.coverage_reasons({"hours_review_due": 400, "hours_review_opened": 0})))
        self.assertTrue(IR.coverage_reasons({"render_attempts": 10, "render_errors": 4}))
        self.assertEqual(IR.coverage_reasons({"render_attempts": 4, "render_errors": 4}), [])
        self.assertEqual(IR.coverage_reasons({}), [])
        self.assertEqual(IR.coverage_reasons({"source_pages": 100, "source_opened": 80}), [])

    def test_thin_read_applies_nothing_and_alerts(self):
        IR.note("foodbanks", source_pages=1685, source_opened=598, budget_skipped=98, hours_review_due=12, hours_review_opened=0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            it, log = self.twice(IM)
        text = buf.getvalue()
        self.assertIn("INTELLIGENT MODE ALERT", text)
        self.assertIn("598 of 1685", text)
        self.assertNotEqual(log["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], OLD["structured"])
        self.assertFalse(it[0]["opening_times"].get("checked_date"))
        md = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("coverage gate", md)
        self.assertNotIn("AUTO-APPLIED", md)
        self.assertFalse(os.path.exists(os.path.join(self.root, "reports", "times_auto_applied.json")))

    def test_mode_off_matches_a_run_without_the_key(self):
        a_root, b_root = tempfile.mkdtemp(), tempfile.mkdtemp()
        it_a, log_a = self.twice(ON, a_root)
        IR.reset()
        it_b, log_b = self.twice({"times_auto_apply": True, "intelligent_mode": False}, b_root)
        self.assertEqual(log_a["a"]["status"], "changed")
        self.assertEqual(log_b["a"]["status"], "changed")
        self.assertEqual(it_a[0]["opening_times"], it_b[0]["opening_times"])
        pa = open(os.path.join(a_root, "reports", "pending_dean.md"), encoding="utf-8").read()
        pb = open(os.path.join(b_root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertEqual(pa, pb)
        self.assertNotIn("INTELLIGENT MODE", pa)
        la = open(os.path.join(a_root, "reports", "times_auto_applied.json"), encoding="utf-8").read()
        lb = open(os.path.join(b_root, "reports", "times_auto_applied.json"), encoding="utf-8").read()
        self.assertEqual(la, lb)

    def test_healthy_intelligent_run_still_applies(self):
        IR.note("foodbanks", source_pages=100, source_opened=100, sites=1, sites_opened=1)
        it, log = self.twice(IM)
        self.assertEqual(log["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], NEW_ST)

    def test_stale_candidate_is_cleared_not_reapplied(self):
        live = {"status": "TIMES_FOUND", "structured": dict(NEW_ST), "raw": "Thursday 2pm - 4pm"}
        it = item(opening_times=dict(live))
        new = {"status": "TIMES_FOUND", "structured": dict(NEW_ST), "raw": "Thursday 2pm - 4pm"}
        os.makedirs(os.path.join(self.root, "logs"))
        json.dump({"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}},
                  open(os.path.join(self.root, "logs", "times_crosscheck_seen.json"), "w"))
        rec = {}
        buf = io.StringIO()
        with redirect_stdout(buf):
            D.times_gate_apply([(it, rec, new, [html()], {"final_url": "https://x.org/", "http": 200})],
                               "fb", "opening_times", "2026-10-29", {}, self.root, IM, R2)
        self.assertEqual(rec["status"], "stale_cleared")
        self.assertEqual(it["opening_times"], live)
        self.assertIn("stale queue cleared fb:a", buf.getvalue())
        md = os.path.join(self.root, "reports", "pending_dean.md")
        self.assertTrue((not os.path.exists(md)) or "fb:a" not in open(md, encoding="utf-8").read() or "AUTO-APPLIED" not in open(md, encoding="utf-8").read())
        IR.reset()
        it2 = item(opening_times=dict(live))
        rec2 = {}
        json.dump({"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}},
                  open(os.path.join(self.root, "logs", "times_crosscheck_seen.json"), "w"))
        D.times_gate_apply([(it2, rec2, dict(new), [html()], {"final_url": "https://x.org/", "http": 200})],
                           "fb", "opening_times", "2026-10-29", {}, self.root, ON, R2)
        self.assertEqual(rec2.get("status"), "changed")
        self.assertIn("checked_date", it2["opening_times"])

    def test_pending_file_drops_a_row_that_already_matches(self):
        os.makedirs(os.path.join(self.root, "reports"))
        row = "- **Riverside** (`a`, AB1 2CD): own site now Thursday 2pm - 4pm  \n  source: https://x.org/  \n  why held: times not read identically on 2 separate runs yet"
        other = "- **Other** (`b`, ZZ9 9ZZ): own site now Monday 9am - 10am  \n  source: https://x.org/  \n  why held: times not read identically on 2 separate runs yet"
        open(os.path.join(self.root, "reports", "pending_dean.md"), "w", encoding="utf-8").write(
            "# Pending for Dean\n\n<!-- times crosscheck fb -->\n## Opening-times changes from the refresh (fb): 0 auto-applied, 2 held\n\n%s\n%s\n<!-- /times crosscheck fb -->\n" % (row, other))
        live = {"a": {"status": "TIMES_FOUND", "structured": dict(NEW_ST), "raw": "Thursday 2pm - 4pm"},
                "b": {"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "11:00"]]}, "raw": "Monday 9am - 11am"}}
        buf = io.StringIO()
        with redirect_stdout(buf):
            cleared = IR.clear_pending_stale(self.root, {"fb": live})
        self.assertEqual(cleared["fb"], ["a"])
        text = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertNotIn("`a`", text)
        self.assertIn("`b`", text)
        self.assertIn("stale queue cleared fb:a", buf.getvalue())

    def test_today_queue_matches_deans_count(self):
        # Frozen 29 Oct 2026 queue (before the 13:39 refresh cleared most food-bank rows).
        os.makedirs(os.path.join(self.root, "reports"))
        pending_path = os.path.join(self.root, "reports", "pending_dean.md")
        data_path = os.path.join(self.root, "data.full.js")
        warm_path = os.path.join(self.root, "warmspaces.js")
        shutil.copy(os.path.join(FIX, "pending_dean.md"), pending_path)
        shutil.copy(os.path.join(FIX, "data.full.js"), data_path)
        shutil.copy(os.path.join(FIX, "warmspaces.js"), warm_path)
        pending = open(pending_path, encoding="utf-8").read()
        fb = {i["id"]: i.get("opening_times") for i in _js(data_path, "=")["items"]}
        ws = {i["id"]: i.get("hours") for i in _js(warm_path, "=")["items"]}
        fb_ids = IR.matching_ids(pending, fb, "times crosscheck fb")
        ws_ids = IR.matching_ids(pending, ws, "times crosscheck ws")
        self.assertEqual(len(ws_ids), 15, ws_ids)
        self.assertGreaterEqual(len(fb_ids), 16, fb_ids)

    def test_strict_checklist_and_locked_fields(self):
        good = {"runs": [{"sig": "a", "source_url": "https://x.org/", "run_at": R1}, {"sig": "a", "source_url": "https://x.org/", "run_at": R2}],
                "own": True, "undo": "python scripts/times_revert.py fb:a", "field": "opening_times"}
        self.assertEqual(IR.strict_reasons(good), [])
        self.assertTrue(any("2 identical" in r for r in IR.strict_reasons(dict(good, runs=good["runs"][:1]))))
        self.assertTrue(any("own source" in r for r in IR.strict_reasons(dict(good, own=False))))
        self.assertTrue(any("conflicting" in r for r in IR.strict_reasons(dict(good, conflict=True))))
        self.assertTrue(any("closed or empty" in r for r in IR.strict_reasons(dict(good, known_hours=True, new_empty=True))))
        self.assertTrue(any("undo" in r for r in IR.strict_reasons(dict(good, undo=""))))
        for field in ("phone", "tel", "council_phone", "council_ooh", "council_label", "council_label_cy"):
            self.assertIn(field, IR.LOCKED_FIELDS)
            self.assertTrue(any("never auto-changed" in r for r in IR.strict_reasons(dict(good, field=field))))
        self.assertEqual(IR.audit_gaps(), [])
        os.makedirs(os.path.join(self.root, "logs"))
        json.dump({"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}},
                  open(os.path.join(self.root, "logs", "times_crosscheck_seen.json"), "w"))
        for field in ("phone", "council_phone", "council_ooh", "council_label", "council_label_cy"):
            it = item()
            rec = {}
            new = {"status": "TIMES_FOUND", "structured": dict(NEW_ST), "raw": "Thursday 2pm - 4pm"}
            D.times_gate_apply([(it, rec, new, [html()], {"final_url": "https://x.org/", "http": 200})],
                               "fb", field, "2026-10-29", {}, self.root, ON, R2)
            self.assertNotIn(field, it)
            self.assertIn("never auto-changed", rec["reason"])

    def test_blast_holds_the_whole_batch(self):
        self.assertEqual(IR.blast_reason(40, "foodbanks", self.root), "")
        self.assertIn("everything held", IR.blast_reason(41, "foodbanks", self.root))
        IR.record_applied("foodbanks", 40)
        self.assertIn("everything held", IR.blast_reason(1, "warmspaces", self.root))
        IR.reset()
        IR.record_applied("warmspaces", 40)
        old = IR.RUN_CAP
        IR.RUN_CAP = 100
        try:
            self.assertIn("warmspaces", IR.blast_reason(1, "warmspaces", self.root))
            self.assertEqual(IR.blast_reason(1, "foodbanks", self.root), "")
        finally:
            IR.RUN_CAP = old

    def test_blast_above_cap_applies_none(self):
        IR.record_applied("foodbanks", 40)
        it, log = self.twice(IM)
        self.assertNotEqual(log["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], OLD["structured"])
        md = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertIn("blast limit", md)
        self.assertNotIn("AUTO-APPLIED", md)

    def test_retry_skips_postcodes_json_and_retries_dns(self):
        calls = {"n": 0}

        def body():
            calls["n"] += 1
            return {"status": 200, "result": [{"query": "AB1 2CD", "result": {"latitude": 1, "longitude": 2}}]}

        self.assertEqual(IR.retry_call(body, sleep=(0, 0, 0))["result"][0]["query"], "AB1 2CD")
        self.assertEqual(calls["n"], 1)
        calls["n"] = 0

        def dns():
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("Temporary failure in name resolution")
            return {"ok": True, "http": 200, "text": "Thursday 2pm - 4pm"}

        self.assertEqual(IR.retry_call(dns, sleep=(0, 0, 0))["http"], 200)
        self.assertEqual(calls["n"], 3)
        calls["n"] = 0

        def missing():
            calls["n"] += 1
            return {"http": 404, "ok": False, "text": ""}

        self.assertEqual(IR.retry_call(missing, sleep=(0, 0, 0))["http"], 404)
        self.assertEqual(calls["n"], 1)
        calls["n"] = 0

        def down():
            calls["n"] += 1
            return {"http": 503, "ok": False, "error": "unavailable"}

        self.assertEqual(IR.retry_call(down, tries=3, sleep=(0, 0, 0))["http"], 503)
        self.assertEqual(calls["n"], 3)

    def test_outage_does_not_mark_closed_or_wipe_times(self):
        self.assertFalse(IR.reading_is_outage({"final_url": "https://x.org/"}))
        self.assertTrue(IR.reading_is_outage({"http": None, "error": "Temporary failure in name resolution"}))
        self.assertTrue(IR.reading_is_outage({"http": 503, "error": "down"}))
        self.assertFalse(IR.reading_is_outage({"http": 200, "final_url": "https://x.org/"}, ["This food bank is permanently closed. " + FILL]))
        closed = html().replace("Emergency food parcels", "This food bank is permanently closed. Emergency food parcels")
        it = [item()]
        log = D.cross_check_times(it, "fb", "opening_times", fetch({"https://x.org/": pg(closed)}), state_root=self.root, rules=ON, run_at=R1)
        self.assertEqual(log["a"]["status"], "closed")
        self.assertTrue(it[0].get("_own_site_closed"))
        it2 = [item()]
        log2 = D.cross_check_times(it2, "fb", "opening_times", fetch({"https://x.org/": pg(closed, error="Temporary failure in name resolution")}),
                                   state_root=self.root, rules=ON, run_at=R1)
        self.assertNotEqual(log2["a"]["status"], "closed")
        self.assertFalse(it2[0].get("_own_site_closed"))
        self.assertEqual(it2[0]["opening_times"]["structured"], OLD["structured"])

    def test_finder_coverage_and_stale(self):
        os.chdir(self.root)
        for folder in ("logs", "reports", "overrides"):
            os.makedirs(folder)
        old_known = TF.known
        TF.known = lambda: {"pages": {}, "skip": {}}
        try:
            IR.note("foodbanks", source_pages=1685, source_opened=598)
            json.dump({"fb1": {"sig": json.dumps({"wed": [["10:00", "12:00"]]}, sort_keys=True), "source_url": "https://testfb.org.uk/opening-times", "run_at": R1}}, open(TF.SEEN, "w"))
            json.dump({}, open("overrides/opening_times.json", "w"))
            ot = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
                  "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27", "fb_mention": True}
            item_f = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
            buf = io.StringIO()
            with redirect_stdout(buf):
                log = {"found": {"fb1": dict(ot)}}
                TF.decide(log, [item_f], False, rules=IM, now=R2)
            self.assertEqual(log["applied"], [])
            self.assertIn("coverage gate", "; ".join(log["review"][0]["why"]))
            self.assertIn("INTELLIGENT MODE ALERT", buf.getvalue())
            IR.reset()
            json.dump({"fb1": ot}, open("overrides/opening_times.json", "w"))
            log2 = {"found": {"fb1": dict(ot)}}
            with redirect_stdout(io.StringIO()):
                TF.decide(log2, [item_f], False, rules=IM, now=R2)
            self.assertEqual(log2["applied"], [])
            self.assertEqual(log2["review"], [])
            IR.reset()
            json.dump({"fb1": {"sig": json.dumps({"wed": [["10:00", "12:00"]]}, sort_keys=True), "source_url": "https://testfb.org.uk/opening-times", "run_at": R1}}, open(TF.SEEN, "w"))
            log3 = {"found": {"fb1": dict(ot)}}
            TF.decide(log3, [dict(item_f)], False, rules=ON, now=R2)
            self.assertEqual(log3["applied"], ["fb1"])
        finally:
            TF.known = old_known

    def test_summary_and_digest(self):
        IR.note("foodbanks", source_pages=1685, source_opened=598, budget_skipped=98)
        data = IR.finish(self.root, "foodbanks", "times", applied=0, held=2, rejected=[{"id": "a", "reasons": ["coverage gate: thin"]}], coverage=IR.merged("foodbanks"))
        self.assertFalse(data["enabled"])
        self.assertEqual(data["layers"]["foodbanks"]["applied"], 0)
        self.assertEqual(data["layers"]["foodbanks"]["held"], 2)
        self.assertTrue(any("598 of 1685" in b for b in data["would_block"]))
        lines = IR.digest_lines(data)
        self.assertTrue(any("INTELLIGENT MODE ALERT" in ln for ln in lines))
        self.assertIn("applied 0", "\n".join(lines))
        import datetime
        import digest
        import learning
        # Digest reads through its own root. Point that at an empty temp folder so a
        # summary written by a real refresh cannot leak into this check.
        digest_root = tempfile.mkdtemp()
        when = datetime.datetime(2026, 10, 29, 8, 0, tzinfo=datetime.timezone.utc)
        old = digest.ROOT, digest.MD, digest.ST, learning.load
        digest.ROOT = digest_root
        digest.MD = os.path.join(digest_root, "morning_digest.md")
        digest.ST = os.path.join(digest_root, "digest_state.json")
        missing = os.path.join(digest_root, "reports", "learning_state.json")
        learning.load = lambda path=None, _missing=missing: old[3](_missing if path is None else path)
        try:
            self.assertFalse(os.path.exists(os.path.join(digest.ROOT, "reports", "intelligent_mode.json")))
            digest.main(when)
            first = open(digest.MD, encoding="utf-8").read()
            self.assertNotIn("## Intelligent mode", first)
            self.assertNotIn("INTELLIGENT MODE ALERT", first)
            os.makedirs(os.path.join(digest_root, "reports"))
            shutil.copy(os.path.join(FIX, "intelligent_mode.json"), os.path.join(digest_root, "reports", "intelligent_mode.json"))
            digest.main(when)
            second = open(digest.MD, encoding="utf-8").read()
            self.assertIn("## Intelligent mode", second)
            self.assertIn("INTELLIGENT MODE ALERT", second)
            self.assertIn("render errors 563 of 563", second)
        finally:
            digest.ROOT, digest.MD, digest.ST, learning.load = old

    def test_access_flip_waits_for_coverage_and_undo(self):
        import full_check as F
        def run(mode, acc):
            items = [dict(id="a", type="foodbank", name="A", foodbank="A", website="https://a.example", postcode="AB1 2CD")]
            store = {"full_check_state.json": {"sites": {"https://a.example": {"access": "voucher", "checked_at": "x"}}, "ids": ["a"]}}
            written = {}
            rep = tempfile.mkdtemp()
            orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.RULES)
            F.rj = lambda n, d: store.get(n, d)
            F.wj = lambda n, o: written.__setitem__(n, o)
            F.load_data = lambda: ("x=", {"items": items})
            F.load_access = lambda: acc
            F.write_md = lambda *a: None
            F.REP = rep
            F.check_site = lambda u: dict(url=u, ok=True, final_url=u, access="voucher", access_evidence="bring a voucher",
                                          hours_hash=None, hours_sample=None, seasonal=None, closed=None, perm_closed=None,
                                          phones=[], tel=None, needs=None, checked_at="y", http=200, fb_mention=True)
            F.RULES = dict(orig[7], intelligent_mode=mode)
            os.environ["DRY_RUN"] = "1"
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    F.main()
            finally:
                F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.RULES = orig
                os.environ.pop("DRY_RUN", None)
            return acc, written, buf.getvalue(), rep
        IR.reset()
        IR.note("foodbanks", source_pages=1685, source_opened=598)
        acc, written, out, rep = run(True, {"a": "walkin"})
        self.assertEqual(acc["a"], "walkin")
        self.assertIn("INTELLIGENT MODE ALERT", out)
        flips = [e for e in written.get("access_changes.json", []) if e.get("id") == "a" and not e.get("kind")]
        self.assertEqual(flips, [])
        blob = json.dumps(written.get("daily_review.json", {}))
        self.assertIn("access flip held (intelligent mode)", blob)
        IR.reset()
        acc2, written2, out2, rep2 = run(False, {"a": "walkin"})
        self.assertEqual(acc2["a"], "voucher")
        self.assertNotIn("INTELLIGENT MODE ALERT", out2)
        flips2 = [e for e in written2.get("access_changes.json", []) if e.get("id") == "a" and not e.get("kind")]
        self.assertEqual(len(flips2), 1)
        self.assertNotIn("revert", flips2[0])
        IR.reset()
        acc3, written3, out3, rep3 = run(True, {"a": "walkin"})
        self.assertEqual(acc3["a"], "voucher")
        self.assertNotIn("INTELLIGENT MODE ALERT", out3)
        flips3 = [e for e in written3.get("access_changes.json", []) if e.get("id") == "a" and not e.get("kind")]
        self.assertEqual(flips3[0]["revert"], "python scripts/access_revert.py a")
        # Logged undo, used when the switch is on.
        os.makedirs(os.path.join(self.root, "reports"))
        os.makedirs(os.path.join(self.root, "overrides"))
        json.dump([dict(id="a", old="walkin", new="voucher")], open(os.path.join(self.root, "reports", "access_changes.json"), "w"))
        json.dump({"a": {"tag": "voucher", "was": "walkin"}}, open(os.path.join(self.root, "reports", "access_tags.json"), "w"))
        open(os.path.join(self.root, "access.js"), "w").write('window.FB_ACCESS={"a":"voucher"};\n')
        import access_revert
        access_revert.revert("a", root=self.root)
        self.assertTrue(json.load(open(os.path.join(self.root, "reports", "access_changes.json")))[0]["reverted"])
        self.assertIn("a", IR.undone_access(self.root))
        self.assertIn('"a":"walkin"', open(os.path.join(self.root, "access.js"), encoding="utf-8").read())


class SweepRetry(unittest.TestCase):
    def test_default_geocoder_retries_then_returns(self):
        import sweep_daily as S
        n = {"n": 0}

        def opener(req, timeout=30):
            n["n"] += 1
            if n["n"] < 3:
                raise OSError("Temporary failure in name resolution")
            return io.BytesIO(json.dumps({"result": [{"query": "AB1 2CD", "result": {"latitude": 52.0, "longitude": 0.1}}]}).encode())

        old = IR._DELAYS
        IR._DELAYS = (0, 0, 0)
        try:
            got = S.geo(["AB1 2CD"], opener=opener)
        finally:
            IR._DELAYS = old
        self.assertEqual(n["n"], 3)
        self.assertEqual(got["AB1 2CD"]["latitude"], 52.0)


if __name__ == "__main__":
    unittest.main()
