"""Own-site hours on the one apply path (the strict gate): two identical runs write and log an undo, a miss keeps the
stored week, known times never become empty or closed, and a phone clash does not block hours."""
import hashlib, json, os, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import discover, learning

R1, R2 = "2026-10-27T03:00:00+00:00", "2026-10-27T11:00:00+00:00"
ON = {"times_auto_apply": True}
def page(html, http=200, final=None, url="https://x.org/"):
    return {"http": http, "final_url": final or url, "html": html, "etag": "e", "last_modified": "", "sha256": hashlib.sha256(html.encode()).hexdigest()}
def fake(site_map):
    def f(u):
        for k, v in site_map.items():
            if u.rstrip("/") == k.rstrip("/"): return v
        return {"http": 404, "final_url": u, "html": ""}
    return f
FILL = " lorem ipsum" * 40
FB = "<html><body><h1>Riverside Food Bank</h1><p>We give emergency food parcels. Riverside Hall, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm.</p>" + FILL + "</body></html>"
WED = "Wednesday 9am - 11am"
THU = "Thursday 2pm - 4pm"

def week_of(html):
    return FB.replace("Tuesday 10am - 12pm, Friday 1pm - 3pm", html)

class HoursConfirm(unittest.TestCase):
    OT = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}}
    def setUp(self):
        self.root = tempfile.mkdtemp()
    def items(self, ot=None):
        return [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
                 "phone": "01234 567890", "opening_times": json.loads(json.dumps(ot or self.OT))}]
    def check(self, it, html=None, run_at=R1, fetcher=None):
        if fetcher is None: fetcher = fake({"https://x.org/": page(html if html is not None else FB)})
        return discover.cross_check_times(it, "fb", "opening_times", fetcher, state_root=self.root, rules=ON, run_at=run_at)
    def twice(self, it, html=None, fetcher=None):
        self.check(json.loads(json.dumps(it)), html, R1, fetcher)
        return self.check(it, html, R2, fetcher)
    def auto_log(self):
        p = os.path.join(self.root, "reports", "times_auto_applied.json")
        return json.load(open(p)) if os.path.exists(p) else []
    def assert_kept(self, it, log):
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("all_closed", it[0]["opening_times"])
        self.assertTrue(it[0]["opening_times"]["structured"])
        self.assertNotEqual(it[0]["opening_times"].get("status"), "")
        self.assertNotIn("pending", log["a"])
        self.assertNotIn("undo", log["a"])
        self.assertNotEqual(log["a"].get("status"), "changed")
        self.assertFalse(log["a"].get("auto_applied"))
        self.assertEqual(self.auto_log(), [])
        self.assertEqual(it[0]["phone"], "01234 567890")

    def test_known_times_never_become_empty_or_closed(self):
        i = self.items()[0]
        home = {"final_url": "https://x.org/"}
        for new in ({}, None, {"structured": {"mon": []}}, {"status": "CLOSED", "structured": {}},
                    {"all_closed": True, "structured": {"mon": [["09:00", "17:00"]]}}):
            why = discover.times_gate_reasons(i, "fb", "opening_times", new, [week_of(WED)], home, {}, {}, True, R1)
            self.assertIn("would change known times to closed/empty", why, new)
        why = discover.times_gate_reasons(i, "fb", "opening_times", {"status": "TIMES_FOUND", "structured": {"wed": [["09:00", "11:00"]]}},
                                          [week_of(WED)], home, {}, {}, True, R1)
        self.assertNotIn("would change known times to closed/empty", why)
        for html in (FB.replace("We give", "This food bank is permanently closed. We gave"), week_of("Closed until further notice"),
                     week_of("Monday 9am - 9am")):
            it = self.items()
            log = self.twice(it, html)
            self.assert_kept(it, log)

    def test_missing_page_keeps_stored_week(self):
        it = self.items()
        log = self.twice(it, fetcher=fake({}))
        self.assertEqual(log["a"]["status"], "unreachable")
        self.assertEqual(it[0]["times_status"], "unconfirmed")
        self.assert_kept(it, log)
        self.assertFalse(it[0]["opening_times"].get("all_closed"))

    def test_unreadable_or_office_like_adds_no_pending_dean_row(self):
        d = tempfile.mkdtemp()
        marker = os.path.join(d, "pending_dean.md")
        open(marker, "w", encoding="utf-8").write("KEEP\n")
        old = os.getcwd()
        try:
            os.chdir(d)
            vague = self.items()
            log = self.twice(vague, week_of("see Facebook for times"))
            self.assertEqual(log["a"]["status"], "unconfirmed")
            self.assert_kept(vague, log)
            self.assertFalse(os.path.exists(os.path.join(self.root, "reports", "pending_dean.md")))   # nothing read, no row
            office = self.items()
            log = self.twice(office, week_of("Monday - Friday 9am - 5pm"))
            self.assertEqual(log["a"]["status"], "held_for_dean")
            self.assertIn("new own-site times look like office/centre hours", log["a"]["held"])
            self.assertNotIn("all_closed", office[0]["opening_times"])
            self.assert_kept(office, log)
            sentence = self.items()
            log = self.twice(sentence, "Riverside Food Bank AB1 2CD. Our office is open Monday - Friday 9am - 5pm." + FILL)
            self.assertEqual(log["a"]["status"], "unconfirmed")
            self.assert_kept(sentence, log)
            closed = self.items()
            log = self.twice(closed, FB.replace("We give", "This food bank is permanently closed. We gave"))
            self.assertEqual(log["a"]["status"], "closed")
            self.assertEqual(closed[0]["opening_times"]["structured"], self.OT["structured"])
            self.assertFalse(closed[0]["opening_times"].get("all_closed"))
            self.assertNotIn("pending", log["a"])
            self.assertEqual(open(marker, encoding="utf-8").read(), "KEEP\n")
            self.assertFalse(os.path.exists(os.path.join(d, "reports", "pending_dean.md")))
        finally:
            os.chdir(old)

    def test_postcode_miss_or_second_run_mismatch_is_not_written(self):
        off = self.items()
        log = self.twice(off, week_of(WED).replace("AB1 2CD", "ZZ9 9ZZ"))
        self.assert_kept(off, log)
        self.setUp()
        blank = self.items(); blank[0]["postcode"] = ""
        log = self.twice(blank, week_of(WED))
        self.assertEqual(blank[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotEqual(log["a"]["status"], "changed")
        self.assertNotIn("undo", log["a"])
        self.assertEqual(self.auto_log(), [])
        self.setUp()
        first = self.items()
        log1 = self.check(first, week_of(WED), R1)
        self.assertEqual(log1["a"]["status"], "held_for_dean")
        self.assertIn("times not read identically on 2 separate runs yet", log1["a"]["held"])
        self.assertEqual(first[0]["opening_times"]["structured"], self.OT["structured"])
        other = self.items()
        log2 = self.check(other, week_of(THU), R2)
        self.assertEqual(log2["a"]["status"], "held_for_dean")
        self.assertIn("times not read identically on 2 separate runs yet", log2["a"]["held"])
        self.assertEqual(other[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("undo", log2["a"])
        self.assertEqual(self.auto_log(), [])

    def test_same_table_on_two_runs_writes_and_logs_undo(self):
        it = self.items()
        old = json.loads(json.dumps(it[0]["opening_times"]))
        html = week_of(WED)
        log1 = self.check(it, html, R1)
        self.assertEqual(log1["a"]["status"], "held_for_dean")
        self.assertEqual(it[0]["opening_times"]["structured"], old["structured"])
        self.assertEqual(self.auto_log(), [])
        log2 = self.check(it, html, R2)
        self.assertEqual(log2["a"]["status"], "changed")
        self.assertTrue(log2["a"]["auto_applied"])
        self.assertEqual(it[0]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})
        self.assertEqual(it[0]["opening_times"]["source_url"], "https://x.org/")
        self.assertEqual(it[0]["times_status"], "updated")
        rec, = self.auto_log()
        self.assertEqual(rec["old"], old)
        self.assertEqual((rec["source_url"], rec["first_run_at"], rec["second_run_at"]), ("https://x.org/", R1, R2))
        self.assertEqual(rec["revert"], "python scripts/times_revert.py fb:a")
        self.assertTrue(it[0]["opening_times"]["structured"])
        self.assertFalse(it[0]["opening_times"].get("all_closed"))

    def test_same_change_on_later_runs_is_logged_once(self):
        html = week_of(WED)
        for n, run_at in enumerate((R1, R2, "2026-10-27T19:00:00+00:00", "2026-10-28T03:00:00+00:00")):
            it = self.items()   # the feed rebuild puts the old week back every run
            log = self.check(it, html, run_at)
            if n: self.assertEqual(log["a"]["status"], "changed")
        self.assertEqual(len(self.auto_log()), 1)
        md = open(os.path.join(self.root, "reports", "pending_dean.md"), encoding="utf-8").read()
        self.assertEqual(md.count("AUTO-APPLIED `a`"), 1)

    def test_phone_conflict_holds_the_phone_and_does_not_blank_hours(self):
        rules = json.load(open(os.path.join(R, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
        site = "https://x.org/"
        self.assertEqual(learning.confidence_for(site, {site}), 0.0)
        self.assertFalse(learning.allow_under_rules("clear single new phone on own site", rules, 0.0))
        it = self.items()
        log2 = self.twice(it, week_of(WED).replace("AB1 2CD.", "AB1 2CD. Call 07700 900123."))
        self.assertEqual(log2["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})
        self.assertEqual(it[0]["phone"], "01234 567890")
        missed = self.items()
        log = self.check(missed, fetcher=fake({}))
        self.assertEqual(missed[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertEqual(missed[0]["phone"], "01234 567890")
        self.assertNotIn("pending", log["a"])
        disc = open(os.path.join(R, "scripts", "discover.py"), encoding="utf-8").read()
        self.assertNotIn("confidence_for", disc)
        self.assertNotIn("allow_under_rules('opening times'", disc)
        self.assertNotIn("client_week", disc)   # one hours-apply path: times_gate_apply
        self.assertEqual(disc.count("def times_gate_apply"), 1)
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("allow_under_rules('clear single new phone on own site'", fc)
        self.assertNotIn("allow_under_rules('opening times'", fc)
        build = open(os.path.join(R, "scripts", "build.py"), encoding="utf-8").read()
        self.assertIn("discover.cross_check_times(items, 'fb', 'opening_times', state_root=ROOT)", build)
        self.assertNotIn("seen=", build)

    def test_first_sight_writes_nothing(self):
        it = self.items()
        log = self.check(it, week_of(WED))
        self.assertEqual(log["a"]["status"], "held_for_dean")
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("undo", log["a"])
        self.assertEqual(self.auto_log(), [])
        it = self.items()   # no saved state at all can never meet the 2-run rule
        log = discover.cross_check_times(it, "fb", "opening_times", fake({"https://x.org/": page(week_of(WED))}), state_root=None, rules=ON, run_at=R2)
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotEqual(log["a"]["status"], "changed")

    def test_one_table_for_two_branches_is_not_applied_on_the_second_run(self):
        it = [{"id": b, "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
               "opening_times": json.loads(json.dumps(self.OT))} for b in ("a", "b")]
        html = week_of(THU)
        log1 = self.check(it, html, R1)
        log2 = self.check(it, html, R2)
        for log in (log1, log2):
            for b in ("a", "b"):
                self.assertEqual(log[b]["status"], "held_for_dean")
                self.assertIn("own site gives one table for several branches; cannot tell which branch", log[b]["held"])
        for row in it: self.assertEqual(row["opening_times"]["structured"], self.OT["structured"])
        self.assertEqual(self.auto_log(), [])

if __name__ == "__main__": unittest.main()
