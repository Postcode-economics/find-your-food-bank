"""times_finder --render calls render_fetch.fetch from 12 worker threads. Playwright's sync API only works on the thread
that started it: sweep run 40823719214 (29 Oct 2026) logged 68 'greenlet.error: cannot switch to a different thread' and
those Trussell centre cards were never read. Every render now runs on one thread that owns the browser."""
import concurrent.futures as cf, http.server, importlib, os, sys, threading, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


class ThreadBound(Exception):
    pass


def fake_playwright(calls):
    """Stands in for playwright.sync_api: every object refuses to be used from a thread other than the one that started it."""
    owner = {}
    def check():
        if threading.get_ident() != owner["t"]: raise ThreadBound("cannot switch to a different thread")
        calls.append(threading.get_ident())
    class Resp:
        status = 200
    class Page:
        def __init__(self): self.url = ""
        def goto(self, url, **kw): check(); self.url = url; return Resp()
        def wait_for_selector(self, *a, **kw): check()
        def wait_for_timeout(self, *a): check()
        def content(self): check(); return "<html>%s</html>" % self.url
        def close(self): check()
    class Browser:
        def new_page(self, **kw): check(); return Page()
        def close(self): check()
    class Chromium:
        def launch(self, **kw): check(); calls.append("launch"); return Browser()
    class PW:
        chromium = Chromium()
        def stop(self): check()
    class Starter:
        def start(self): owner["t"] = threading.get_ident(); return PW()
    mod = types.ModuleType("playwright.sync_api"); mod.sync_playwright = lambda: Starter()
    pkg = types.ModuleType("playwright"); pkg.sync_api = mod
    return {"playwright": pkg, "playwright.sync_api": mod}


class RenderFromManyThreads(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in ("playwright", "playwright.sync_api")}
        self.calls = []
        sys.modules.update(fake_playwright(self.calls))
        import render_fetch
        self.rf = importlib.reload(render_fetch)
    def tearDown(self):
        self.rf.close()
        for k, v in self.saved.items():
            if v is None: sys.modules.pop(k, None)
            else: sys.modules[k] = v

    def test_twelve_worker_threads_all_get_their_page(self):
        urls = ["https://site%d.foodbank.org.uk/emergency-food/i-have-a-food-voucher" % n for n in range(36)]
        with cf.ThreadPoolExecutor(12) as ex:
            got = list(ex.map(self.rf.fetch, urls))
        self.assertEqual(got, [(200, u, "<html>%s</html>" % u) for u in urls])
        self.assertEqual(self.calls.count("launch"), 1)   # one browser for the whole run
        self.assertEqual(len({c for c in self.calls if c != "launch"}), 1)   # every browser call on the same thread

    def test_close_then_fetch_again_starts_a_new_browser(self):
        self.assertEqual(self.rf.fetch("https://a.org/")[0], 200)
        self.rf.close()
        self.assertEqual(self.rf.fetch("https://b.org/")[0], 200)
        self.assertEqual(self.calls.count("launch"), 2)

    def test_a_crashed_render_returns_the_empty_result_and_the_worker_keeps_going(self):
        real = self.rf._render
        def boom(*a): raise SystemExit("renderer crashed")
        self.rf._render = boom
        try:
            self.assertEqual(self.rf.fetch("https://x.org/"), (0, "https://x.org/", ""))
        finally:
            self.rf._render = real
        self.assertEqual(self.rf.fetch("https://y.org/")[0], 200)


def _have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(args=["--no-sandbox"]).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_chromium(), "Playwright + Chromium not installed (installed in the sweep step)")
class RealBrowser(unittest.TestCase):
    def test_real_chromium_from_worker_threads(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                b = ("<html><body><h2>Collection times</h2><p>%s</p></body></html>" % self.path).encode()
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b)
            def log_message(self, *a): pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        for k in ("playwright", "playwright.sync_api"):
            m = sys.modules.get(k)
            if m is not None and not hasattr(m, "__file__"): sys.modules.pop(k)
        import render_fetch
        rf = importlib.reload(render_fetch)
        try:
            urls = ["http://127.0.0.1:%d/centre-%d" % (srv.server_port, n) for n in range(8)]
            with cf.ThreadPoolExecutor(6) as ex:
                got = list(ex.map(lambda u: rf.fetch(u, tries=1, wait_ms=1000), urls))
            for u, (code, final, html) in zip(urls, got):
                self.assertEqual(code, 200)
                self.assertIn("/centre-", html)
                self.assertIn(u.rsplit("/", 1)[1], html)
        finally:
            rf.close(); srv.shutdown()


if __name__ == "__main__":
    unittest.main()
