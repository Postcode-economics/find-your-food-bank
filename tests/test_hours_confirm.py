"""Own-site hours: two matching runs write, a miss keeps the stored week, a phone clash does not block hours."""
import hashlib, json, os, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import discover, learning

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
    def items(self, ot=None):
        return [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
                 "phone": "01234 567890", "opening_times": json.loads(json.dumps(ot or self.OT))}]
    def check(self, it, html=None, seen=None, fetcher=None):
        if fetcher is None: fetcher = fake({"https://x.org/": page(html if html is not None else FB)})
        return discover.cross_check_times(it, "fb", "opening_times", fetcher, seen=seen)
    def assert_kept(self, it, log):
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("all_closed", it[0]["opening_times"])
        self.assertTrue(it[0]["opening_times"]["structured"])
        self.assertNotEqual(it[0]["opening_times"].get("status"), "")
        self.assertNotIn("pending", log["a"])
        self.assertNotIn("undo", log["a"])
        self.assertEqual(it[0]["phone"], "01234 567890")

    def test_client_week_rejects_empty_and_closed(self):
        self.assertFalse(discover.client_week({}))
        self.assertFalse(discover.client_week(None))
        self.assertFalse(discover.client_week({"structured": {"mon": []}}))
        self.assertFalse(discover.client_week({"structured": {"mon": [["09:00", "09:00"]]}}))
        self.assertFalse(discover.client_week({"all_closed": True, "structured": {"mon": [["09:00", "17:00"]]}}))
        self.assertTrue(discover.client_week({"structured": {"wed": [["09:00", "11:00"]]}}))

    def test_missing_page_keeps_stored_week(self):
        it = self.items()
        log = self.check(it, fetcher=fake({}), seen={})
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
            log = self.check(vague, week_of("see Facebook for times"), seen={})
            self.assertEqual(log["a"]["status"], "unconfirmed")
            self.assert_kept(vague, log)
            office = self.items()
            log = self.check(office, week_of("Monday - Friday 9am - 5pm"), seen={})
            self.assertEqual(log["a"]["status"], "unconfirmed")
            self.assertIn("stored week kept", log["a"]["reason"])
            self.assert_kept(office, log)
            sentence = self.items()
            log = self.check(sentence, "Riverside Food Bank AB1 2CD. Our office is open Monday - Friday 9am - 5pm." + FILL, seen={})
            self.assertEqual(log["a"]["status"], "unconfirmed")
            self.assert_kept(sentence, log)
            closed = self.items()
            log = self.check(closed, FB.replace("We give", "This food bank is permanently closed. We gave"), seen={})
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
        html = week_of(WED).replace("AB1 2CD", "ZZ9 9ZZ")
        log1 = self.check(off, html, seen={})
        self.assert_kept(off, log1)
        log2 = self.check(off, html, seen={"a": log1["a"].get("pending") or {}})
        self.assert_kept(off, log2)
        blank = self.items(); blank[0]["postcode"] = ""
        log1 = self.check(blank, week_of(WED), seen={})
        self.assertEqual(log1["a"]["status"], "seen_once")
        self.assertEqual(blank[0]["opening_times"]["structured"], self.OT["structured"])
        log2 = self.check(blank, week_of(WED), seen={"a": log1["a"]["pending"]})
        self.assertNotEqual(log2["a"]["status"], "changed")
        self.assertEqual(blank[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("undo", log2["a"])
        first = self.items()
        log1 = self.check(first, week_of(WED), seen={})
        self.assertEqual(log1["a"]["status"], "seen_once")
        self.assertEqual(first[0]["opening_times"]["structured"], self.OT["structured"])
        other = self.items()
        log2 = self.check(other, week_of(THU), seen=json.loads(json.dumps({"a": log1["a"]["pending"]})))
        self.assertEqual(log2["a"]["status"], "seen_once")
        self.assertEqual(other[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("undo", log2["a"])

    def test_same_table_on_two_runs_writes_and_logs_undo(self):
        it = self.items()
        old = json.loads(json.dumps(it[0]["opening_times"]["structured"]))
        html = week_of(WED)
        log1 = self.check(it, html, seen={})
        self.assertEqual(log1["a"]["status"], "seen_once")
        self.assertEqual(it[0]["opening_times"]["structured"], old)
        self.assertNotIn("undo", log1["a"])
        self.assertEqual(log1["a"]["pending"]["postcode"], "AB12CD")
        seen = json.loads(json.dumps({"a": log1["a"]["pending"]}))
        log2 = self.check(it, html, seen=seen)
        self.assertEqual(log2["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})
        self.assertEqual(it[0]["times_status"], "updated")
        self.assertEqual(log2["a"]["undo"]["structured"], old)
        self.assertTrue(it[0]["opening_times"]["structured"])
        self.assertFalse(it[0]["opening_times"].get("all_closed"))

    def test_phone_conflict_holds_the_phone_and_does_not_blank_hours(self):
        rules = json.load(open(os.path.join(R, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
        site = "https://x.org/"
        self.assertEqual(learning.confidence_for(site, {site}), 0.0)
        self.assertFalse(learning.allow_under_rules("clear single new phone on own site", rules, 0.0))
        it = self.items()
        html = week_of(WED)
        log1 = self.check(it, html, seen={})
        log2 = self.check(it, html, seen={"a": log1["a"]["pending"]})
        self.assertEqual(log2["a"]["status"], "changed")
        self.assertEqual(it[0]["opening_times"]["structured"], {"wed": [["09:00", "11:00"]]})
        self.assertEqual(it[0]["phone"], "01234 567890")
        missed = self.items()
        log = self.check(missed, fetcher=fake({}), seen={})
        self.assertEqual(missed[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertEqual(missed[0]["phone"], "01234 567890")
        self.assertNotIn("pending", log["a"])
        disc = open(os.path.join(R, "scripts", "discover.py"), encoding="utf-8").read()
        self.assertNotIn("confidence_for", disc)
        self.assertNotIn("allow_under_rules('opening times'", disc)
        self.assertNotIn("pending_dean", disc)
        fc = open(os.path.join(R, "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("allow_under_rules('clear single new phone on own site'", fc)
        self.assertNotIn("allow_under_rules('opening times'", fc)
        build = open(os.path.join(R, "scripts", "build.py"), encoding="utf-8").read()
        self.assertIn("seen=seen", build)

    def test_empty_pending_log_writes_nothing_on_the_first_sight(self):
        prev = {"a": {"status": "changed", "new": {"wed": [["09:00", "11:00"]]}}, "b": {"status": "confirmed"}}
        seen = {k: v.get("pending") for k, v in prev.items() if isinstance(v, dict) and isinstance(v.get("pending"), dict)}
        self.assertEqual(seen, {})
        it = self.items()
        log = self.check(it, week_of(WED), seen=seen)
        self.assertEqual(log["a"]["status"], "seen_once")
        self.assertEqual(it[0]["opening_times"]["structured"], self.OT["structured"])
        self.assertNotIn("undo", log["a"])

    def test_one_table_for_two_branches_is_not_applied_on_the_second_run(self):
        it = [{"id": b, "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
               "opening_times": json.loads(json.dumps(self.OT))} for b in ("a", "b")]
        html = week_of(THU)
        log1 = self.check(it, html, seen={})
        self.assertEqual({log1["a"]["status"], log1["b"]["status"]}, {"unconfirmed"})
        for row in it: self.assertEqual(row["opening_times"]["structured"], self.OT["structured"])

if __name__ == "__main__": unittest.main()
