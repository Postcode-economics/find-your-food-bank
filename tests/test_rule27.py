"""Rule 27 on the three-times-daily sweep (scripts/full_check.py) and the source-page check.

Offline fixtures only. Nothing here opens a network socket or a browser.
"""
import os, sys, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover
import full_check as F
import hours_audit as A

SRC = "https://bank.example/locations"
HOME = "https://bank.example/"
PAGE = "Riverside Food Bank, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm."
BARE = "Riverside Food Bank, 1 High St, AB1 2CD. Ask at the door."
TABLE = {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}
LINE = "Opening times not listed. Call before you go."

def item(structured=None, url=SRC, website=HOME):
    ot = {"status": "TIMES_FOUND", "structured": structured if structured is not None else dict(TABLE), "source_url": url}
    return {"id": "riverside", "type": "foodbank", "name": "Riverside Food Bank", "foodbank": "Riverside Food Bank",
            "postcode": "AB1 2CD", "website": website, "opening_times": ot}

def html(text):
    return "<html><body><p>%s</p></body></html>" % text

class UrlMatch(unittest.TestCase):
    def test_same_page_allows_https_www_and_slash(self):
        self.assertTrue(discover.source_page_ok("http://bank.example/locations", "https://www.bank.example/locations/"))
        self.assertFalse(discover.source_page_ok(SRC, "https://bank.example/voucher"))
        self.assertFalse(discover.source_page_ok(SRC, "https://other.example/locations"))
        self.assertFalse(discover.source_page_ok(SRC, "https://web.archive.org/web/2020/https://bank.example/locations"))
        self.assertFalse(discover.source_page_ok(SRC + "?day=tue", SRC))
        self.assertFalse(discover.source_page_ok(SRC, SRC + "/amp"))

    def test_redirect_is_unclear_and_the_other_page_is_not_read(self):
        def fetch(url):
            self.assertEqual(url, SRC)  # (b) the listing source, not the website homepage
            return {"ok": True, "http": 200, "final_url": "https://webcache.googleusercontent.com/search?q=cache:" + SRC,
                    "html": html(PAGE)}
        page = F.read_source(item(), fetch=fetch, render=lambda u: self.fail("redirect must not be rendered"))
        self.assertEqual(page["text"], "")
        verdict = F.hours_verdict(item(), page)
        self.assertEqual(verdict["status"], "unclear")
        self.assertEqual(verdict["evidence"], "")
        self.assertIn(LINE, verdict["note"])
        self.assertIn("redirected", verdict["note"])

class RenderAndEvidence(unittest.TestCase):
    def test_plain_html_without_a_timetable_is_rendered(self):
        calls = []
        def fetch(url):
            calls.append(("fetch", url))
            return {"ok": True, "http": 200, "final_url": url, "html": html(BARE)}
        def render(url):
            calls.append(("render", url))
            return {"ok": True, "http": 200, "final_url": url, "html": html(PAGE)}
        page = F.read_source(item(), fetch=fetch, render=render)
        self.assertEqual(calls, [("fetch", SRC), ("render", SRC)])
        self.assertTrue(page["rendered"])
        verdict = F.hours_verdict(item(), page)
        self.assertEqual(verdict["status"], "verified")
        self.assertIn(verdict["evidence"], PAGE)
        self.assertIn("Tuesday", verdict["evidence"])

    def test_complete_plain_html_is_not_rendered(self):
        def fetch(url):
            return {"ok": True, "http": 200, "final_url": url, "html": html(PAGE)}
        page = F.read_source(item(), fetch=fetch, render=lambda u: self.fail("render"))
        self.assertFalse(page.get("rendered"))
        verdict = F.hours_verdict(item(), page)
        self.assertEqual(verdict["status"], "verified")
        self.assertTrue(verdict["evidence"])
        self.assertIn(verdict["evidence"], PAGE)

    def test_mismatch_is_unclear_even_when_day_text_would_hash(self):
        # Old sweep: hash the day-shaped lines and call the card verified when the hash was unchanged.
        # Friday-only on the card, Tuesday and Friday on the page: the page has day text, and it still does not confirm.
        fri = item({"fri": [["13:00", "15:00"]]})
        page = {"ok": True, "http": 200, "final_url": SRC, "text": PAGE}
        verdict = F.hours_verdict(fri, page)
        self.assertEqual(verdict["status"], "unclear")
        self.assertEqual(verdict["evidence"], "")
        self.assertIn(LINE, verdict["note"])
        self.assertTrue(F.DAYS.search(PAGE))

    def test_live_open_failure_does_not_fall_back(self):
        page = F.read_source(item(), fetch=lambda u: {"ok": False, "http": 403, "error": "HTTP 403", "html": html(PAGE), "final_url": u}, render=None)
        verdict = F.hours_verdict(item(), page)
        self.assertEqual(verdict["status"], "unclear")
        self.assertEqual(verdict["evidence"], "")
        self.assertNotIn("Tuesday", verdict["evidence"])
        self.assertIn(LINE, verdict["note"])

class SweepState(unittest.TestCase):
    def _run(self, check, prev_site, fetch):
        it = item()
        store = {"full_check_state.json": {"sites": {HOME: prev_site}, "ids": ["riverside"], "hours": {
            "riverside": {"status": "verified", "evidence": "stale monday 9-5", "source_url": SRC}}}}
        written = {}
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.fetch, F.review_hours)
        F.rj = lambda n, d: store.get(n, d)
        F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ("x=", {"items": [it]})
        F.load_access = lambda: {}
        F.write_md = lambda *a: None
        F.REP = tempfile.mkdtemp()
        F.check_site = lambda u: check
        F.fetch = fetch
        orig_review = F.review_hours
        F.review_hours = lambda items, state, flag, deadline, fetch=None, render=None: orig_review(
            items, state, flag, deadline, fetch=F.fetch, render=lambda u: {"ok": False, "html": ""})
        os.environ["DRY_RUN"] = "1"
        try:
            F.main()
        finally:
            F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site, F.fetch, F.review_hours = orig
            os.environ.pop("DRY_RUN", None)
        return written, it

    def test_failed_fetch_does_not_keep_previous_hours(self):
        prev = {"access": "voucher", "hours_hash": "abc", "hours_sample": ["friday 1-3"], "seasonal": "closed over christmas", "hours_status": "verified", "phones": ["01234567890"]}
        written, it = self._run({"url": HOME, "ok": False, "http": 403, "error": "HTTP 403"}, prev, lambda u: {"ok": False, "http": 403, "error": "HTTP 403"})
        site = written["full_check_state.json"]["sites"][HOME]
        self.assertEqual(site["access"], "voucher")  # 2-run access state is kept
        self.assertEqual(site["hours_hash"], "")
        self.assertEqual(site["hours_sample"], [])
        self.assertIsNone(site["seasonal"])
        self.assertEqual(site["hours_status"], "unclear")
        hours = written["full_check_state.json"]["hours"]["riverside"]
        self.assertEqual(hours["status"], "unclear")
        self.assertEqual(hours["evidence"], "")
        self.assertNotEqual(hours["evidence"], "stale monday 9-5")
        self.assertIn(LINE, hours["note"])
        self.assertEqual(it["opening_times"]["structured"], TABLE)

    def test_skipped_site_is_not_left_verified(self):
        prev = {"access": "walkin", "hours_hash": "abc", "hours_sample": ["friday 1-3"], "seasonal": "bank holiday", "hours_status": "verified"}
        written, it = self._run({"url": HOME, "ok": None, "error": "time budget reached - not checked this run"}, prev, lambda u: {"ok": False, "error": "budget"})
        site = written["full_check_state.json"]["sites"][HOME]
        self.assertEqual(site["access"], "walkin")
        self.assertEqual(site["hours_hash"], "")
        self.assertEqual(site.get("hours_status"), "unclear")
        hours = written["full_check_state.json"]["hours"]["riverside"]
        self.assertEqual(hours["status"], "unclear")
        self.assertEqual(hours["evidence"], "")
        self.assertIn(LINE, hours["note"])
        notes = " ".join((v.get("note") or "") for v in written["daily_review.json"][F.DAY]["items"].values())
        self.assertIn("not checked this run", notes)
        self.assertEqual(it["opening_times"]["structured"]["fri"], [["13:00", "15:00"]])

    def test_budget_skip_does_not_call_the_source(self):
        called = []
        state = {"hours": {"riverside": {"status": "verified", "evidence": "old quote"}}}
        flags = {}
        def flag(key, cat, **kw):
            flags[cat + "|" + key] = kw
        n = F.review_hours([item()], state, flag, deadline=0, fetch=lambda u: called.append(u), render=lambda u: called.append(u))
        self.assertEqual(called, [])
        self.assertEqual(n, 1)
        self.assertEqual(state["hours"]["riverside"]["status"], "unclear")
        self.assertEqual(state["hours"]["riverside"]["evidence"], "")
        self.assertIn("not checked this run", state["hours"]["riverside"]["note"])

class PolitenessAndTwoRuns(unittest.TestCase):
    def test_gap_and_two_run_rule_stay(self):
        self.assertEqual(F.MIN_GAP, 2.0)
        src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "full_check.py"), encoding="utf-8").read()
        self.assertIn("prev.get('access') == r['access']", src)
        self.assertIn("_hostlock", src)
        import auto_rules
        self.assertEqual(auto_rules.load()["confirm_runs"], 2)

class SourceCheck(unittest.TestCase):
    def test_sweep_redirect_does_not_replace_hours(self):
        it = item({"fri": [["13:00", "15:00"]]})
        seen = []
        def fetcher(url):
            seen.append(url)
            if url.rstrip("/") == HOME.rstrip("/"):
                return {"http": 200, "final_url": HOME, "html": html("homepage only"), "etag": "", "last_modified": "", "sha256": "h"}
            return {"http": 200, "final_url": "https://archive.org/web/1/" + url, "html": html(PAGE), "etag": "", "last_modified": "", "sha256": "a"}
        log = discover.cross_check_times([it], "fb", "opening_times", fetcher=fetcher, threads=1, render=lambda u: self.fail("redirect is not rendered"))
        self.assertEqual(log["riverside"]["status"], "differs_review")
        self.assertIn("redirected", log["riverside"]["reason"])
        self.assertEqual(it["opening_times"]["structured"], {"fri": [["13:00", "15:00"]]})
        self.assertIn(SRC, seen)

    def test_confirmed_hours_carry_an_evidence_quote(self):
        it = item()
        def fetcher(url):
            final = SRC if url.rstrip("/") == SRC.rstrip("/") else url
            return {"http": 200, "final_url": final, "html": html(PAGE), "etag": "", "last_modified": "", "sha256": "p"}
        log = discover.cross_check_times([it], "fb", "opening_times", fetcher=fetcher, threads=1, render=lambda u: self.fail("complete html is not rendered"))
        self.assertEqual(log["riverside"]["status"], "confirmed", log["riverside"].get("reason"))
        quote = log["riverside"].get("evidence") or ""
        self.assertTrue(quote)
        self.assertIn(quote, PAGE)
        self.assertEqual(it["opening_times"]["structured"], TABLE)

    def test_audit_row_uses_the_quote_or_unclear(self):
        rec = {"http": 200, "final_url": SRC, "url": SRC, "text": PAGE}
        self.assertIsNone(A.row_for(item(), rec, False))  # stored table matches; nothing to apply
        # An extra office day is on the page. The parser skips it, so the new table would not account for every day listed.
        mixed = PAGE + " Our office is open Monday 9am - 5pm."
        bad = A.row_for(item({"fri": [["13:00", "15:00"]]}), dict(rec, text=mixed), False)
        self.assertEqual(bad["decision"], "review")
        self.assertTrue(bad["note"].startswith("unclear:"))
        self.assertEqual(bad["source_hours"], "")
        self.assertEqual(bad["structured"], {})
        self.assertIn(LINE, bad["note"])
        jumped = dict(rec, final_url="https://archive.org/web/x")
        row = A.row_for(item(), jumped, False)
        self.assertTrue(row["note"].startswith("unclear:"))
        self.assertIn("redirected", row["note"])
        self.assertEqual(row["evidence"], "")

if __name__ == "__main__":
    unittest.main()
