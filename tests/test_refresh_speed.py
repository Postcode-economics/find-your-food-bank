"""Refresh time budget (run 40821758973, 29 Oct 2026: the rebuild step took 68 min instead of ~10 and the job hit its
90 min timeout in the full check). The live source-url reads ran one listing at a time and every 403 slept 65 s.

Offline fixtures only: fake fetchers with a fixed delay stand in for the network.
"""
import os, re, sys, threading, time, unittest, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover
import full_check as F

PAGE = "<html><body><p>Riverside Food Bank, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm.</p></body></html>"
TABLE = {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}
N, DELAY = 120, 0.03   # one at a time: >= N * DELAY = 3.6 s

def listings(n=N, hosts=12):
    out = []
    for k in range(n):
        src = "https://bank%d.example/centre-%d" % (k % hosts, k)
        out.append({"id": "bank%d/centre-%d" % (k % hosts, k), "type": "location", "name": "Riverside Food Bank",
                    "foodbank": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "",
                    "opening_times": {"status": "TIMES_FOUND", "structured": dict(TABLE), "source_url": src}})
    return out

class Gauge:
    """Fake live fetch: fixed delay, counts calls and the most reads in flight on one host."""
    def __init__(self):
        self.calls, self.now, self.peak, self.lock = [], {}, {}, threading.Lock()
    def __call__(self, url):
        h = discover.host(url)
        with self.lock:
            self.calls.append(url); self.now[h] = self.now.get(h, 0) + 1
            self.peak[h] = max(self.peak.get(h, 0), self.now[h])
        time.sleep(DELAY)
        with self.lock: self.now[h] -= 1
        return {"ok": True, "http": 200, "final_url": url, "html": PAGE, "etag": "", "last_modified": "", "sha256": "p"}

def strip(log):
    return {k: {f: v for f, v in r.items() if f != "checked"} for k, r in log.items()}

class RebuildSourceReads(unittest.TestCase):
    def test_source_reads_run_in_parallel_one_live_read_each(self):
        g = Gauge(); items = listings()
        t = time.monotonic()
        log = discover.cross_check_times(items, "fb", "opening_times", fetcher=g, render=lambda u: self.fail("complete page is not rendered"))
        took = time.monotonic() - t
        self.assertLess(took, N * DELAY / 3, "source-url reads are running one at a time again (%.1fs)" % took)
        self.assertEqual(sorted(g.calls), sorted(i["opening_times"]["source_url"] for i in items))
        self.assertLessEqual(max(g.peak.values()), discover.SOURCE_PER_HOST)
        self.assertEqual(len(log), N)

    def test_parallel_result_is_identical_to_one_at_a_time(self):
        fast_items, slow_items = listings(36), listings(36)
        fast = discover.cross_check_times(fast_items, "fb", "opening_times", fetcher=Gauge(), render=lambda u: {})
        slow = discover.cross_check_times(slow_items, "fb", "opening_times", fetcher=Gauge(), render=lambda u: {}, threads=1)
        self.assertEqual(strip(fast), strip(slow))
        self.assertEqual(fast_items, slow_items)

    def test_renders_are_capped(self):
        live, peak, lock = [0], [0], threading.Lock()
        def render(u):
            with lock: live[0] += 1; peak[0] = max(peak[0], live[0])
            time.sleep(0.02)
            with lock: live[0] -= 1
            return {}
        bare = lambda u: {"http": 200, "final_url": u, "html": "<p>Riverside Food Bank AB1 2CD. Ask at the door.</p>"}
        discover.read_sources(listings(24), "fb", "opening_times", bare, render, 24)
        self.assertLessEqual(peak[0], discover.SOURCE_RENDERS)

class BoundedRetries(unittest.TestCase):
    def setUp(self):
        self.orig = (discover._open, discover._sleep); discover._refused.clear()
    def tearDown(self):
        discover._open, discover._sleep = self.orig; discover._refused.clear()

    def test_a_host_that_refuses_every_retry_stops_costing_sleeps(self):
        slept, opened = [], []
        def refuse(url, headers):
            opened.append(url)
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        discover._open, discover._sleep = refuse, slept.append
        pages = ["https://centre%d.foodbank.org.uk/locations/" % k for k in range(40)]
        out = [discover._request(u) for u in pages]
        self.assertTrue(all(r["http"] == 403 and not r["html"] for r in out))
        self.assertEqual(len(slept), discover.RETRY_GIVE_UP * discover.RETRY_TRIES)
        self.assertLessEqual(sum(slept), discover.RETRY_GIVE_UP * sum(discover.retry_delay(n) for n in range(1, discover.RETRY_TRIES + 1)))
        self.assertEqual(len(opened), len(pages) + len(slept))
        r = discover._request("https://other.example/hours")   # another host still gets its polite retries
        self.assertEqual(r.get("retries"), discover.RETRY_TRIES)

    def test_cloudflare_challenge_is_not_retried(self):
        slept = []
        def challenge(url, headers):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {"cf-mitigated": "challenge"}, None)
        discover._open, discover._sleep = challenge, slept.append
        r = discover._request("https://centre.foodbank.org.uk/locations/")
        self.assertEqual((r["http"], r["html"], slept, r.get("retries")), (403, "", [], None))
        self.assertEqual(discover.review_category({"status": "unreachable", "http": 403}), "blocked_after_retries")

    def test_a_retry_that_gets_through_is_not_counted(self):
        tries = {}
        def once(url, headers):
            tries[url] = tries.get(url, 0) + 1
            if tries[url] == 1: raise urllib.error.HTTPError(url, 429, "Too Many", {}, None)
            class R:
                status = 200; headers = {}
                def read(self, n): return b"<p>ok</p>"
                def geturl(self): return url
            return R()
        discover._open, discover._sleep = once, lambda s: None
        for k in range(5): self.assertEqual(discover._request("https://slow.example/p%d" % k)["http"], 200)
        self.assertEqual(discover._refused.get("slow.example", 0), 0)

class FullCheckHours(unittest.TestCase):
    def _review(self, threads):
        g = Gauge(); state, flags = {}, []
        orig = (F.fetch, F.HOURS_THREADS, dict(F._robots_cache))
        F.fetch = g; F.HOURS_THREADS = threads; F._robots_cache.clear()
        try:
            t = time.monotonic()
            n = F.review_hours(listings(), state, lambda key, cat, **kw: flags.append((key, cat)), deadline=time.time() + 600, fetch=g, render=lambda u: {})
            return n, state, flags, time.monotonic() - t
        finally:
            F.fetch, F.HOURS_THREADS = orig[0], orig[1]; F._robots_cache.clear(); F._robots_cache.update(orig[2])

    def test_hours_review_runs_in_parallel_with_the_same_verdicts(self):
        n, state, flags, took = self._review(F.HOURS_THREADS)
        n1, state1, flags1, _ = self._review(1)
        self.assertEqual(n, N)
        self.assertLess(took, N * DELAY / 3, "full check hours review is running one listing at a time again (%.1fs)" % took)
        strip_t = lambda s: {k: {f: v for f, v in r.items() if f != "checked_at"} for k, r in s["hours"].items()}
        self.assertEqual(strip_t(state), strip_t(state1))
        self.assertEqual(flags, flags1)
        self.assertEqual({r["status"] for r in state["hours"].values()}, {"verified"})

class WorkflowBudget(unittest.TestCase):
    def test_rebuild_step_has_its_own_timeout_inside_the_job(self):
        with open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "refresh.yml"), encoding="utf-8") as fh: wf = fh.read()
        job = int(re.search(r"^    timeout-minutes: (\d+)", wf, re.M).group(1))
        step = wf[wf.index("- name: Rebuild data.js"):]
        step = step[:step.index("\n      - name:")]
        m = re.search(r"timeout-minutes: (\d+)", step)
        self.assertIsNotNone(m, "the rebuild step must have its own timeout")
        # rebuild budget + the full check's own BUDGET_S + the sense check (~9 min) and tests (~7 min) fit inside the job
        self.assertLessEqual(int(m.group(1)) + F.BUDGET / 60 + 16, job)
        self.assertNotIn("timeout-minutes", wf[wf.index("- name: Full check"):wf.index("- name: Anomaly brake")],
                         "a killed full check would skip the anomaly brake; it is bounded by its own BUDGET_S")

    def test_run_failed_alert_also_fires_on_cancel_or_timeout(self):
        with open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "refresh.yml"), encoding="utf-8") as fh: wf = fh.read()
        step = wf[wf.index("- name: Alert - run failed (nothing new published)"):]
        cond = re.search(r"if: (.+)", step[:step.index("\n      - name:")]).group(1)
        self.assertIn("cancelled()", cond)
        self.assertIn("failure()", cond)
        self.assertIn("steps.commit.outcome != 'success'", cond)

if __name__ == "__main__":
    unittest.main()
