"""Shown dates come from each layer's own refresh stamp (Dean, 25 Oct 2026): header = latest refresh of any layer,
footer food bank lines = food bank refresh, key = each layer's refresh (shelters/warm spaces even before opening).
No date is hardcoded in the page; stamp.py keeps per-layer stamps; the watchdog compares shown dates with the data."""
import os, re, json, shutil, subprocess, sys, tempfile, unittest, threading, functools, http.server, mimetypes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import check_browser as B
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
M = '(January|February|March|April|May|June|July|August|September|October|November|December)'
DATE = re.compile(r'\b\d{1,2} ' + M + r'( 20\d\d)?|' + M + r' 20\d\d|\b20\d\d-\d\d-\d\d\b')

class NoHardcodedDates(unittest.TestCase):
    def test_sources(self):
        for f in ("index.html", "layers.js", "v3.js"):
            s = open(os.path.join(ROOT, f), encoding="utf-8").read()
            s = re.sub(r'<script type="application/ld\+json".*?</script>', '', s, flags=re.S)  # baked by seo_meta.py each run
            s = re.sub(r'(<a id="freshtxt"[^>]*>)[^<]*', '', s)                                  # baked by seo_meta.py each run
            self.assertEqual([m.group(0) for m in DATE.finditer(s)], [], f)

class StampLayers(unittest.TestCase):
    def test_write_keeps_each_layer(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "stamp.py"), os.path.join(d, "scripts"))
        open(os.path.join(d, "stamp.js"), "w").write('window.FB_STAMP={"run":"2026-10-25T05:12:51+00:00","kind":"refresh","label":"x","layers":{"fb":{"run":"2026-10-25T05:12:51+00:00","label":"x"},"sh":{"run":"2026-10-24T22:03:27+01:00","label":"y"}}};\n')
        subprocess.run([sys.executable, os.path.join(d, "scripts", "stamp.py"), "write", "warmspaces"], check=True, capture_output=True)
        s = json.loads(open(os.path.join(d, "stamp.js")).read().split("=", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(s["kind"], "warmspaces"); self.assertEqual(s["layers"]["ws"]["run"], s["run"])
        self.assertEqual(s["layers"]["fb"]["run"], "2026-10-25T05:12:51+00:00"); self.assertEqual(s["layers"]["sh"]["run"], "2026-10-24T22:03:27+01:00")
        subprocess.run([sys.executable, os.path.join(d, "scripts", "stamp.py"), "write", "sweep"], check=True, capture_output=True)
        s2 = json.loads(open(os.path.join(d, "stamp.js")).read().split("=", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(s2["layers"], s["layers"])  # a sweep is not a layer refresh
    def test_committed_stamp_has_layers(self):
        s = json.loads(open(os.path.join(ROOT, "stamp.js")).read().split("=", 1)[1].rstrip().rstrip(";"))
        self.assertTrue({"fb", "sh", "ws"} <= set(s.get("layers", {})))
    def test_combine_keeps_the_later_date_of_each_layer(self):
        # 26 Oct: the food-bank refresh rebased with -X theirs and replaced stamp.js outright,
        # so the shelters and warm-space refreshes from the same morning disappeared.
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import stamp
        fb = {"run": "2026-10-26T05:55:03+00:00", "kind": "refresh", "label": "26 Oct 2026, 05:55",
              "layers": {"fb": {"run": "2026-10-26T05:55:03+00:00", "label": "26 Oct 2026, 05:55"},
                         "ws": {"run": "2026-10-25T05:19:00+00:00", "label": "old"},
                         "sh": {"run": "2026-10-25T05:19:45+00:00", "label": "old"}}}
        sh = {"run": "2026-10-26T05:34:43+00:00", "kind": "shelters", "label": "26 Oct 2026, 05:34",
              "layers": {"fb": {"run": "2026-10-25T21:43:05+00:00", "label": "old"},
                         "ws": {"run": "2026-10-26T05:32:27+00:00", "label": "26 Oct 2026, 05:32"},
                         "sh": {"run": "2026-10-26T05:34:43+00:00", "label": "26 Oct 2026, 05:34"}}}
        m = stamp.combine(fb, sh)
        self.assertEqual(m["layers"]["fb"]["run"], "2026-10-26T05:55:03+00:00")
        self.assertEqual(m["layers"]["ws"]["run"], "2026-10-26T05:32:27+00:00")
        self.assertEqual(m["layers"]["sh"]["run"], "2026-10-26T05:34:43+00:00")
        self.assertEqual(m["run"], "2026-10-26T05:55:03+00:00")
        for rel in (".github/workflows/refresh.yml", ".github/workflows/refresh-shelters.yml",
                    ".github/workflows/refresh-warmspaces.yml", ".github/workflows/sweep-daily.yml"):
            y = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertNotIn("pull --rebase -X theirs", y, rel)
            self.assertIn("refresh_rebase_conflicts.sh", y, rel)

class Watchdog(unittest.TestCase):
    def _mod(self):
        import importlib.util as u
        sp = u.spec_from_file_location("alert_mod", os.path.join(ROOT, "scripts", "alert.py")); m = u.module_from_spec(sp); sp.loader.exec_module(m); return m
    def test_current_data_ok(self):
        self.assertEqual(self._mod().date_problems(), [])
    def test_catches_stale(self):
        d = tempfile.mkdtemp()
        for f in ("data.js", "shelters.js", "warmspaces.js"): shutil.copy(os.path.join(ROOT, f), d)
        open(os.path.join(d, "stamp.js"), "w").write('window.FB_STAMP={"run":"2026-10-25T05:19:45+00:00","kind":"shelters","label":"25 October 2026, 05:19","layers":{"fb":{"run":"2020-01-01T00:00:00+00:00","label":"old"},"sh":{"run":"2026-10-25T05:19:45+00:00","label":"z"}}};')
        p = self._mod().date_problems(root=d, live='window.FB_STAMP={"run":"2026-10-24T22:03:27+01:00","label":"24 October 2026, 22:03"};')
        self.assertTrue(any(x.startswith("fb:") for x in p), p); self.assertTrue(any("no ws" in x for x in p), p); self.assertTrue(any("behind main" in x for x in p), p)
    def test_in_watchdog(self):
        self.assertIn("python scripts/alert.py dates", open(os.path.join(ROOT, ".github", "workflows", "watchdog.yml")).read())

FAKE = 'window.FB_STAMP={"run":"2031-03-07T09:41:00+00:00","kind":"shelters","label":"7 March 2031, 09:41","layers":{"fb":{"run":"2031-03-06T08:15:00+00:00","label":"6 March 2031, 08:15"},"ws":{"run":"2031-03-07T09:40:00+00:00","label":"7 March 2031, 09:40"},"sh":{"run":"2031-03-07T09:41:00+00:00","label":"7 March 2031, 09:41"}}};'
class Browser(unittest.TestCase):
    def test_lines_follow_stamp(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        H = "https://fyfb.local/"
        def serve(r):
            u = r.request.url
            if not u.startswith(H): return r.abort()
            path = u[len(H):].split("?")[0] or "index.html"
            if path == "stamp.js": return r.fulfill(status=200, body=FAKE, content_type="application/javascript")
            p = os.path.join(ROOT, path)
            if not os.path.isfile(p): return r.fulfill(status=404, body="")
            r.fulfill(status=200, body=open(p, "rb").read(), content_type=mimetypes.guess_type(p)[0] or "application/octet-stream")
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = c.new_page(); pg.route("**/*", serve)
            B.stub_map_tiles(pg)  # after the catch-all, so a tile URL is the placeholder and not an aborted network request
            pg.goto(H + "index.html?fresh=1", wait_until="load"); pg.wait_for_timeout(2500)
            g = lambda s: pg.evaluate("s=>{const e=document.querySelector(s);return e?e.textContent:''}", s)
            self.assertIn("7 March 2031", g("#freshtxt")); self.assertIn("09:41", g("#freshtxt"))   # latest of all layers
            self.assertEqual(g("#chk"), "checked 6 March 2031, 08:15")                              # food bank refresh
            self.assertEqual(g("#upd"), "6 March 2031, 08:15")
            self.assertIn("2031", g("#u_fb")); self.assertIn("2031", g("#u_ws")); self.assertIn("2031", g("#u_sh"))  # key: always a date
            self.assertNotIn("tap to show", g("#u_sh"))
            b.close()
