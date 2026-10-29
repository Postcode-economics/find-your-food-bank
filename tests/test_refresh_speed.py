"""Refresh time budget (run 40821758973, 29 Oct 2026: the rebuild step took 68 min instead of ~10 and the job hit its
90 min timeout in the full check). The live source-url reads ran one listing at a time and every 403 slept 65 s.

Offline: discover._open (the socket) is replaced by a fixed-delay fake, so every read still goes through the real
fetch_live -> _request path (polite retry included). Nothing here opens a network socket or a browser.
"""
import os, re, sys, threading, time, unittest, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover

TABLE = {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}
FULL = "<html><body><p>Riverside Food Bank, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm.</p></body></html>"
BARE = "<html><body><p>Riverside Food Bank, 1 High St, AB1 2CD. Ask at the door.</p></body></html>"
OTHER = "<html><body><p>Riverside Food Bank, 1 High St, AB1 2CD. Monday 9am - 11am.</p></body></html>"
N, DELAY = 120, 0.03   # one at a time: >= N * DELAY = 3.6 s

def src_url(k):
    if k % 2: return "https://centre%d.foodbank.org.uk/locations/c%d/" % (k % 10, k)   # Trussell: one shared server
    return "https://bank%d.example/centre-%d" % (k % 12, k)

def listings(n=N):
    return [{"id": "fb%d/centre-%d" % (k % 12, k), "type": "location", "name": "Riverside Food Bank %d" % k,
             "foodbank": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "",
             "opening_times": {"status": "TIMES_FOUND", "structured": dict(TABLE), "source_url": src_url(k)}} for k in range(n)]

class Resp:
    def __init__(self, url, body): self.url, self.body, self.status, self.headers = url, body, 200, {}
    def read(self, n): return self.body.encode()
    def geturl(self): return self.url

class FakeNet:
    """Deterministic answer per URL: complete page, page with no timetable (rendered), different times, plain 403
    (polite retries), Cloudflare challenge 403, 429 then OK. Records reads in flight per site."""
    def __init__(self):
        self.lock, self.now, self.peak, self.opens, self.seen = threading.Lock(), {}, {}, [], {}
    def kind(self, url):
        k = int(re.search(r"(\d+)/?$", url).group(1))
        return ("full", "bare", "other", "403", "challenge", "429-once", "full")[k % 7]
    def __call__(self, url, headers):
        site = discover.site_key(url)
        with self.lock:
            self.opens.append(url); self.now[site] = self.now.get(site, 0) + 1
            self.peak[site] = max(self.peak.get(site, 0), self.now[site]); n = self.seen[url] = self.seen.get(url, 0) + 1
        try:
            time.sleep(DELAY)
            kind = self.kind(url)
            if kind == "403": raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            if kind == "challenge": raise urllib.error.HTTPError(url, 403, "Forbidden", {"cf-mitigated": "challenge"}, None)
            if kind == "429-once" and n == 1: raise urllib.error.HTTPError(url, 429, "Too Many", {"Retry-After": "1"}, None)
            return Resp(url, {"bare": BARE, "other": OTHER}.get(kind, FULL))
        finally:
            with self.lock: self.now[site] -= 1

def render(u):
    return {"ok": True, "http": 200, "final_url": u, "html": FULL if int(re.search(r"(\d+)/?$", u).group(1)) % 3 else BARE}

def strip(log):
    return {k: {f: v for f, v in r.items() if f != "checked"} for k, r in log.items()}

class RealRequestPath(unittest.TestCase):
    def setUp(self):
        self.orig = (discover._open, discover._sleep)
        discover._sleep = lambda s: None
    def tearDown(self):
        discover._open, discover._sleep = self.orig

    def run_check(self, threads):
        net = FakeNet(); discover._open = net; items = listings()
        t = time.monotonic()
        log = discover.cross_check_times(items, "fb", "opening_times", threads=threads, render=render)
        return items, log, net, time.monotonic() - t

    def test_parallel_output_is_identical_to_one_at_a_time(self):
        par_items, par_log, par_net, _ = self.run_check(24)
        ser_items, ser_log, ser_net, _ = self.run_check(1)
        self.assertEqual(strip(par_log), strip(ser_log))
        self.assertEqual(par_items, ser_items)
        self.assertEqual(sorted(par_net.opens), sorted(ser_net.opens))   # same live reads and retries, nothing reused
        statuses = {r["status"] for r in par_log.values()}
        self.assertGreater(len(statuses), 1, statuses)   # the fixture covers more than one outcome

    def test_source_reads_are_parallel_and_capped_per_site(self):
        items, log, net, took = self.run_check(24)
        self.assertLess(took, N * DELAY / 3, "source-url reads are running one at a time again (%.1fs)" % took)
        self.assertEqual(len(log), N)
        self.assertLessEqual(net.peak["foodbank.org.uk"], discover.SOURCE_PER_SITE)   # all Trussell subdomains together
        self.assertLessEqual(max(net.peak.values()), discover.SOURCE_PER_SITE)
        srcs = [i["opening_times"]["source_url"] for i in items]
        self.assertTrue(set(srcs) <= set(net.opens))

    def test_trussell_subdomains_are_one_site(self):
        self.assertEqual(discover.site_key("https://coventry.foodbank.org.uk/x"), discover.site_key("https://www.barnsley.foodbank.org.uk/"))
        self.assertEqual(discover.site_key("https://www.bank.example/x"), "bank.example")

    def test_renders_are_capped(self):
        live, peak, lock = [0], [0], threading.Lock()
        def slow_render(u):
            with lock: live[0] += 1; peak[0] = max(peak[0], live[0])
            time.sleep(0.02)
            with lock: live[0] -= 1
            return {}
        bare = lambda u: {"http": 200, "final_url": u, "html": BARE}
        discover.read_sources(listings(24), "fb", "opening_times", bare, slow_render, 24)
        self.assertLessEqual(peak[0], discover.SOURCE_RENDERS)

class Retries(unittest.TestCase):
    def setUp(self):
        self.orig = (discover._open, discover._sleep)
    def tearDown(self):
        discover._open, discover._sleep = self.orig

    def test_cloudflare_challenge_is_not_retried(self):
        slept = []
        def challenge(url, headers):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {"cf-mitigated": "challenge"}, None)
        discover._open, discover._sleep = challenge, slept.append
        r = discover._request("https://centre.foodbank.org.uk/locations/")
        self.assertEqual((r["http"], r["html"], slept, r.get("retries")), (403, "", [], None))
        self.assertEqual(discover.review_category({"status": "unreachable", "http": 403}), "blocked_after_retries")

    def test_every_other_refusal_keeps_its_full_polite_retries(self):
        slept = []
        def refuse(url, headers):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        discover._open, discover._sleep = refuse, slept.append
        for k in range(5):
            self.assertEqual(discover._request("https://c%d.foodbank.org.uk/locations/" % k).get("retries"), discover.RETRY_TRIES)
        self.assertEqual(len(slept), 5 * discover.RETRY_TRIES)
        src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "discover.py"), encoding="utf-8").read()
        self.assertNotIn("RETRY_GIVE_UP", src)

class WorkflowBudget(unittest.TestCase):
    def wf(self):
        with open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "refresh.yml"), encoding="utf-8") as fh: return fh.read()
    def step(self, wf, name):
        s = wf[wf.index("- name: " + name):]
        return s[:s.index("\n      - name:")]

    def test_rebuild_step_has_its_own_timeout_inside_the_job(self):
        wf = self.wf()
        job = int(re.search(r"^    timeout-minutes: (\d+)", wf, re.M).group(1))
        self.assertEqual(job, 90)
        m = re.search(r"timeout-minutes: (\d+)", self.step(wf, "Rebuild data.js"))
        self.assertIsNotNone(m, "the rebuild step must have its own timeout")
        self.assertLess(int(m.group(1)), job)
        self.assertNotIn("timeout-minutes", wf[wf.index("- name: Full check"):wf.index("- name: Anomaly brake")],
                         "a killed full check would skip the anomaly brake; it is bounded by its own BUDGET_S")

    def test_run_failed_alert_also_fires_on_cancel_or_timeout(self):
        cond = re.search(r"if: (.+)", self.step(self.wf(), "Alert - run failed (nothing new published)")).group(1)
        self.assertIn("cancelled()", cond)
        self.assertIn("failure()", cond)
        self.assertIn("steps.commit.outcome != 'success'", cond)

if __name__ == "__main__":
    unittest.main()
