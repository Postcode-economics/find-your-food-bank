"""Public page claims match the code and data (Dean, 25 Oct 2026): FAQ times come from the workflow crons (UTC -> UK time,
GMT and BST), SWEP figures are baked from data, no season-only wording, the 44x44 touch claim holds, label texts match."""
import os, re, sys, json, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rd = lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read()
def cron(wf):
    m = re.search(r'cron:\s*"(\d+) ([\d,]+) \* \* \*"', rd(os.path.join(".github", "workflows", wf))); return int(m.group(1)), [int(h) for h in m.group(2).split(",")]
def fmt(h, mi):
    h %= 24; return f"{h % 12 or 12}:{mi:02d}{'am' if h < 12 else 'pm'}"
def times(wf, offset, round5=True):
    mi, hs = cron(wf)
    if round5: t = [h * 60 + mi for h in hs]; t = [round(x / 5) * 5 for x in t]; return [fmt(x // 60 + offset, x % 60) for x in t]
    return [fmt(h + offset, mi) for h in hs]

class Faq(unittest.TestCase):
    def setUp(self): self.s = rd("faq.html")
    def test_refresh_times_from_cron(self):
        for off in (0, 1):  # GMT, BST
            a, b, c = times("refresh.yml", off)
            self.assertIn(f"{a}, {b} and {c}", self.s, off)
        f, _ = cron("refresh.yml"); sh, _ = cron("refresh-shelters.yml"); ws, _ = cron("refresh-warmspaces.yml")
        self.assertIn(f"about {sh - f} minutes later and warm spaces about {ws - sh} minutes after", self.s)
    def test_sweep_times_from_cron(self):
        for off in (0, 1):
            a, b, c = times("sweep-daily.yml", off, round5=False)
            self.assertIn(f"{a}, {b} and {c}", self.s, off)
    def test_no_season_only_wording(self):
        for bad in ("UK summer time", "amser haf y DU", "64 councils", "64 o gynghorau"):
            self.assertNotIn(bad, self.s)
    def test_swep_counts_baked_from_data(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts")); import seo_meta
        n = seo_meta.swep_counts(ROOT); self.assertEqual(set(n), {"swep-councils", "swep-pages"})
        for k, v in n.items():
            got = re.findall(r'<span data-n="%s">([^<]*)</span>' % k, self.s)
            self.assertEqual(len(got), 2, k); self.assertTrue(all(g == format(v, ",") for g in got), (k, got, v))
    def test_swep_never_changes_map(self):
        self.assertIn("never changes the map", rd(os.path.join(".github", "workflows", "refresh-shelters.yml")))
        self.assertNotIn("swep", (rd("layers.js") + rd("v3.js") + rd("index.html")).lower())
    def test_label_texts_explained(self):
        lj = rd("layers.js")
        for en in ("Unverified – call before you go", "Times checked {d} – call before you go"):
            self.assertIn(en, lj); self.assertIn("“" + en.replace("{d}", "&lt;date&gt;") + "”", self.s)

class Footer(unittest.TestCase):
    def test_no_own_website_overclaim(self):
        self.assertNotIn("checked on each food bank's own website", rd("index.html"))

class TouchTargets(unittest.TestCase):
    def test_all_buttons_44(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        self.assertIn("at least 44 by 44 pixels", rd("accessibility.html"))
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
                for w in (390, 1366):
                    pg = b.new_page(viewport={"width": w, "height": 844}); open_map(pg, f"http://127.0.0.1:{srv.server_address[1]}/?fresh=1"); pg.wait_for_timeout(1500)
                    pg.evaluate("()=>nearest(50.8095,-0.5405,'BN17 5LF')"); pg.wait_for_timeout(800)
                    small = pg.evaluate("()=>[...document.querySelectorAll('button, a.btn, .fchip, label.tog')].filter(e=>e.offsetParent!==null&&!e.closest('.leaflet-container')).map(e=>{const r=e.getBoundingClientRect();return [e.id||String(e.className).slice(0,30),Math.round(r.width),Math.round(r.height)]}).filter(x=>x[1]&&(x[1]<44||x[2]<44))")
                    self.assertEqual(small, [], w)
                b.close()
        finally: srv.shutdown()
