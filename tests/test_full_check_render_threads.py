"""full_check.review_hours calls render_polite from up to 12 host worker threads. Playwright's sync API only works on
the thread that started it; discover.render_live from every worker failed every hours-review render in refresh run
40912857173 (568 render_errors of 568). render_polite must use render_fetch.fetch like times_finder --render."""
import concurrent.futures as cf, importlib, json, os, sys, tempfile, threading, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


class ThreadBound(Exception):
    pass


def fake_playwright(calls):
    owner = {}
    def check():
        if threading.get_ident() != owner["t"]:
            raise ThreadBound("cannot switch to a different thread")
        calls.append(threading.get_ident())
    class Resp:
        status = 200
    class Page:
        def __init__(self):
            self.url = ""
        def goto(self, url, **kw):
            check()
            self.url = url
            return Resp()
        def wait_for_selector(self, *a, **kw):
            check()
        def wait_for_timeout(self, *a):
            check()
        def content(self):
            check()
            return "<html>%s</html>" % self.url
        def close(self):
            check()
    class Browser:
        def new_page(self, **kw):
            check()
            return Page()
        def close(self):
            check()
    class Chromium:
        def launch(self, **kw):
            check()
            calls.append("launch")
            return Browser()
    class PW:
        chromium = Chromium()
        def stop(self):
            check()
    class Starter:
        def start(self):
            owner["t"] = threading.get_ident()
            return PW()
    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = lambda: Starter()
    pkg = types.ModuleType("playwright")
    pkg.sync_api = mod
    return {"playwright": pkg, "playwright.sync_api": mod}


class FullCheckRenderThreads(unittest.TestCase):
    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in ("playwright", "playwright.sync_api")}
        self.calls = []
        sys.modules.update(fake_playwright(self.calls))
        import render_fetch
        self.rf = importlib.reload(render_fetch)
        import full_check as F
        self.F = importlib.reload(F)
        for d in (F._locks, F._last, F._errs, F._paused):
            d.clear()
        F.MIN_GAP = 0

    def tearDown(self):
        self.rf.close()
        self.F.MIN_GAP = 2.0
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_render_polite_from_twelve_threads(self):
        urls = ["https://bank%d.example/page" % n for n in range(24)]
        with cf.ThreadPoolExecutor(12) as ex:
            got = list(ex.map(self.F.render_polite, urls))
        self.assertTrue(all(r.get("ok") and r.get("html") for r in got))
        self.assertEqual(self.calls.count("launch"), 1)
        self.assertEqual(len({c for c in self.calls if c != "launch"}), 1)

    def test_parallel_renders_are_not_all_errors(self):
        """Coverage gate must not see 100% render failure when workers call render_polite."""
        import intelligent_rails as IR
        IR.reset()
        urls = ["https://bank%d.example/page" % n for n in range(16)]
        with cf.ThreadPoolExecutor(12) as ex:
            list(ex.map(self.F.render_polite, urls))
        stats = IR.merged("foodbanks", local_render=True)
        att = int(stats.get("render_attempts") or 0)
        err = int(stats.get("render_errors") or 0)
        self.assertEqual(att, len(urls))
        self.assertLess(err, att, "every render was counted as failed (thread/greenlet regression)")

    def test_local_render_merge_ignores_times_step_tally(self):
        import intelligent_rails as IR
        IR.reset()
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "reports"))
        json.dump({"run": IR._today(), "layers": {"foodbanks": {"coverage": {"render_attempts": 568, "render_errors": 568}}}},
                  open(os.path.join(root, "reports", "intelligent_mode.json"), "w"))
        IR.note_render(True)
        IR.note_render(False)
        m = IR.merged("foodbanks", root, local_render=True)
        self.assertEqual(m.get("render_attempts"), 2)
        self.assertEqual(m.get("render_errors"), 1)
        self.assertNotIn(568, (m.get("render_attempts"), m.get("render_errors")))


if __name__ == "__main__":
    unittest.main()
