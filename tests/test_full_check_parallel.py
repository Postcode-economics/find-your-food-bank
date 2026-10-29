"""full_check.review_hours reads different hosts at the same time (Dean, 29 Oct 2026) and must give exactly what
main's one-listing-at-a-time loop gave: same hours state, same flags in the same order, and the same request
sequence on every host (so _polite's 2 s gap, 3-errors-then-10-min pause and the 429 ledger see the same thing).

Everything goes through the real fetch -> _polite -> _urllib_load path, robots.txt and render_polite included.
Only urllib.request.urlopen (the socket) and the headless browser are faked. Timings are shuffled per run.
"""
import io, os, random, re, sys, threading, time, unittest, urllib.error
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover, rate_ledger
import full_check as F

FULL = "Riverside Food Bank, 1 High St, AB1 2CD. Tuesday 10am - 12pm, Friday 1pm - 3pm."
BARE = "Riverside Food Bank, 1 High St, AB1 2CD. Ask at the door."
FRI = "Riverside Food Bank, 1 High St, AB1 2CD. Friday 1pm - 3pm."
TABLE = {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}

def html(t): return "<html><body><p>%s</p></body></html>" % t

def host_for(k):
    if k % 9 == 0: return "bad.example"                        # every page errors: 3 errors in a row pause it
    if k % 9 == 1: return "www.mixed.example" if k % 2 else "mixed.example"   # one ledger host, two _polite hosts
    if k % 3 == 0: return "c%d.foodbank.org.uk" % (k % 5)      # Trussell, shared 2-slot cap
    return "bank%d.example" % (k % 7)

def listings(n):
    out = []
    for k in range(n):
        h = host_for(k)
        out.append({"id": "fb/%d" % k, "type": "location" if k % 4 else "foodbank", "name": "Riverside %d" % k, "postcode": "AB1 2CD",
                    "opening_times": {"status": "TIMES_FOUND", "structured": dict(TABLE), "source_url": "https://%s/centre-%d" % (h, k)}})
    out.insert(5, {"id": "shelter/x", "type": "shelter", "opening_times": {"source_url": "https://bank1.example/s"}})
    out.insert(9, {"id": "fb/nosrc", "type": "foodbank", "opening_times": {"status": "TIMES_FOUND"}})
    return out

class Resp(io.BytesIO):
    def __init__(self, url, body):
        super().__init__(body.encode()); self.url, self.status = url, 200
        self.headers = mock.Mock(get_content_charset=lambda: "utf-8")
    def geturl(self): return self.url
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

class Net:
    def __init__(self, seed):
        self.rnd, self.lock = random.Random(seed), threading.Lock()
        self.by_host, self.live, self.peak_trussell = {}, 0, 0
    def urlopen(self, req, timeout=None):
        url = req.full_url; h = F.polite_host(url)
        with self.lock:
            self.by_host.setdefault(h, []).append(url); d = self.rnd.uniform(0, 0.006)
            if h.endswith("foodbank.org.uk"): self.live += 1; self.peak_trussell = max(self.peak_trussell, self.live)
        try:
            time.sleep(d)
            if h == "bad.example": raise urllib.error.HTTPError(url, 500, "err", {}, None)
            if url.endswith("/robots.txt"):
                if h.startswith("c1."): return Resp(url, "User-agent: *\nDisallow: /centre-12")
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            k = int(re.search(r"centre-(\d+)", url).group(1))
            if k % 11 == 4: raise urllib.error.HTTPError(url, 429, "slow", {}, None)
            if k % 7 == 5: raise urllib.error.URLError("timed out")
            if k % 13 == 6: return Resp("https://elsewhere.example/x", html(FULL))
            return Resp(url, html((FULL, BARE, FRI)[k % 3]))
        finally:
            if h.endswith("foodbank.org.uk"):
                with self.lock: self.live -= 1

def fake_render_fetch(u):
    k = int(re.search(r"centre-(\d+)", u).group(1))
    if k % 2 == 0:
        return 200, u, html(FULL if k % 4 == 0 else "")
    return 0, u, ""

def main_serial(items, state, flag, deadline, fetch=None, render=None):
    """main's review_hours loop before 29 Oct, verbatim apart from the names."""
    fetch = fetch or F.fetch
    render = render if render is not None else F.render_polite
    state.setdefault('hours', {})
    n = 0
    for i in items:
        if i.get('type') not in ('foodbank', 'location'): continue
        src = F.listing_source_url(i)
        if not src: continue
        n += 1
        if time.time() > deadline:
            state['hours'][i['id']] = {'status': 'unclear', 'evidence': '', 'source_url': src, 'final_url': '',
                                       'note': 'unclear: not checked this run; previous hours are not verified. ' + F.UNCLEAR_LINE,
                                       'rendered': False, 'checked_at': F.NOW.isoformat()}
            continue
        verdict = F.hours_verdict(i, F.read_source(i, fetch=fetch, render=render))
        state['hours'][i['id']] = {'status': verdict['status'], 'evidence': verdict.get('evidence') or '', 'source_url': src,
                                   'final_url': verdict.get('final_url') or '', 'note': verdict.get('note') or '',
                                   'rendered': bool(verdict.get('rendered')), 'checked_at': F.NOW.isoformat()}
        if verdict['status'] != 'verified':
            flag(i['id'], 'opening times unclear', name=i.get('name') or '', website=src, id=i['id'],
                 note=verdict.get('note') or '', evidence=verdict.get('evidence') or '')
    return n

class Parallel(unittest.TestCase):
    def setUp(self):
        import render_fetch
        self.saved = (F.MIN_GAP, F.TRUSSELL, rate_ledger.LEDGER, render_fetch.fetch)
        F.MIN_GAP = 0.004   # the real gap logic, shortened
    def tearDown(self):
        import render_fetch
        F.MIN_GAP, F.TRUSSELL, rate_ledger.LEDGER, render_fetch.fetch = self.saved
        self.reset()
    def reset(self):
        for d in (F._locks, F._last, F._errs, F._paused, F._robots_cache): d.clear()
        F.TRUSSELL = threading.Semaphore(2); rate_ledger.LEDGER = rate_ledger.Ledger()

    def run_once(self, fn, seed, n=90, deadline=None):
        self.reset(); net = Net(seed); state, flags = {}, []
        import render_fetch
        render_fetch.fetch = fake_render_fetch
        with mock.patch("urllib.request.urlopen", net.urlopen):
            t = time.monotonic()
            got = fn(listings(n), state, lambda key, cat, **kw: flags.append((key, cat, sorted(kw.items()))), deadline or time.time() + 600)
            took = time.monotonic() - t
        return dict(n=got, hours=state["hours"], flags=flags, seq=net.by_host, paused=dict(F._paused), errs=dict(F._errs),
                    ledger=(dict(rate_ledger.LEDGER.counts), set(rate_ledger.LEDGER.paused)), took=took, peak=net.peak_trussell)

    def same(self, a, b):
        self.assertEqual(a["n"], b["n"])
        self.assertEqual(a["hours"], b["hours"])
        self.assertEqual(list(a["hours"]), list(b["hours"]))   # written in listing order
        self.assertEqual(a["flags"], b["flags"])
        self.assertEqual(a["seq"], b["seq"])                    # every host saw the same requests in the same order
        self.assertEqual(set(a["paused"]), set(b["paused"]))
        self.assertEqual(a["errs"], b["errs"])
        self.assertEqual(a["ledger"], b["ledger"])

    def test_identical_to_mains_serial_loop_with_shuffled_timings(self):
        for seed in (1, 2, 3):
            ref = self.run_once(main_serial, seed)
            par = self.run_once(F.review_hours, seed + 100)
            self.same(par, ref)
        statuses = {v["status"] for v in ref["hours"].values()}
        notes = " ".join(v["note"] for v in ref["hours"].values())
        self.assertEqual(statuses, {"verified", "unclear"})
        self.assertIn("paused for 10 min", notes)               # the pause-after-3-errors case is exercised
        self.assertIn("bad.example", ref["paused"])
        self.assertIn("redirected", notes)
        self.assertTrue(ref["ledger"][1])                       # a 429 paused a host in the ledger
        self.assertTrue(any(v.get("rendered") for v in ref["hours"].values()))

    def test_trussell_cap_holds_and_hosts_run_concurrently(self):
        ref = self.run_once(main_serial, 7, n=180)
        par = self.run_once(F.review_hours, 8, n=180)
        self.same(par, ref)
        self.assertLessEqual(par["peak"], 2)
        self.assertLess(par["took"], ref["took"] / 2.5, "review_hours is reading one host at a time (%.2fs vs %.2fs)" % (par["took"], ref["took"]))

    def test_budget_skip_matches_when_the_deadline_has_passed(self):
        self.same(self.run_once(F.review_hours, 1, deadline=time.time() - 1), self.run_once(main_serial, 1, deadline=time.time() - 1))

    def test_gap_is_kept_per_host_and_waited_outside_the_trussell_slot(self):
        self.reset(); F.MIN_GAP = 0.2
        held, lock, stamps = [0], threading.Lock(), {}
        def loader(u):
            with lock: stamps.setdefault(F.polite_host(u), []).append(time.monotonic())
            time.sleep(0.01); return {"ok": True}
        ts = [threading.Thread(target=F._polite, args=("https://c%d.foodbank.org.uk/p%d" % (k % 4, k), loader)) for k in range(12)]
        t = time.monotonic(); [x.start() for x in ts]; [x.join() for x in ts]
        self.assertEqual(len(stamps), 4)
        for h, s in stamps.items():
            self.assertTrue(all(b - a >= 0.19 for a, b in zip(s, s[1:])), (h, s))   # 2 s gap (scaled) per host kept
        # 4 Trussell hosts x 3 reads: waiting the gap inside one of the 2 slots takes >= 8 * 0.2 / 2 = 0.8 s
        self.assertLess(time.monotonic() - t, 0.65)
        self.assertEqual(F.MIN_GAP, 0.2); F.MIN_GAP = 0.004

class Unchanged(unittest.TestCase):
    def test_politeness_limits_and_budget_are_unchanged(self):
        self.assertEqual((F.MIN_GAP, F.ERR_LIMIT, F.PAUSE, F.TIMEOUT, F.BUDGET, F.HOURS_BUDGET),
                         (2.0, 3, 600, 15, int(os.environ.get("BUDGET_S", 2400)), int(os.environ.get("HOURS_BUDGET_S", int(os.environ.get("BUDGET_S", 2400))))))
        self.assertEqual(F.TRUSSELL._value, 2)

if __name__ == "__main__":
    unittest.main()
