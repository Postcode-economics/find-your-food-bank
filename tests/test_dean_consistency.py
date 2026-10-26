"""Dean's consistency decisions (25 Oct 2026, 07:48): 'call before you go' everywhere; one date format
'25 Oct 2026, 05:12' (data-driven); hours tables 'Closed' / 'Not listed'; referral-only shelters say
'By referral – call before you go'; footers credit shelter sources; policy 'Last updated' set automatically."""
import os, re, sys, json, glob, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
R = lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read()
UI = ["index.html", "layers.js", "v3.js", "faq.html", "404.html", "scripts/build_seo.py", "scripts/seo_meta.py"]
LONG = r"\b\d{1,2} (January|February|March|April|June|July|August|September|October|November|December) \d{4}"
FMT = r"\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}, \d\d:\d\d"

class Wording(unittest.TestCase):
    def test_call_before_you_go(self):
        for f in UI:
            s = R(f)
            for w in ("call ahead", "call first", "ffoniwch ymlaen llaw", "ffoniwch yn gyntaf"):
                self.assertNotIn(w, s.replace("Call first\\.", ""), (f, w))  # translation key for any old source text is allowed
        pages = glob.glob(os.path.join(ROOT, "*", "*", "index.html"))[:50]
        for p in pages:
            self.assertNotIn("Times change, call ahead", open(p, encoding="utf-8").read(), p)

class Dates(unittest.TestCase):
    def test_one_format(self):
        st = json.loads(R("stamp.js").split("=", 1)[1].rstrip().rstrip(";"))
        for v in [st] + list(st["layers"].values()): self.assertRegex(v["label"], "^" + FMT + "$")
        for f in ["index.html", "faq.html", "privacy.html", "terms.html", "accessibility.html", "404.html"] + glob.glob(os.path.join(ROOT, "*", "*", "index.html"))[:40]:
            s = re.sub(r"<script type=\"application/ld\+json\".*?</script>", "", R(f) if not f.startswith("/") else open(f, encoding="utf-8").read(), flags=re.S)
            self.assertNotRegex(s, LONG, f)
            self.assertNotRegex(s, r"last updated \d{4}-\d\d-\d\d", f)
            for m in re.finditer(r"(?:Last updated|last updated|last checked|Updated) ([^<.]*\d{4}[^<.]*)", s):
                self.assertRegex(m.group(1).strip(), "^" + FMT + "$", (f, m.group(0)))
        self.assertIn("function deanDate", R("index.html")); self.assertNotIn("toLocaleDateString", R("index.html"))
        self.assertNotIn("Updated today at", R("index.html")); self.assertNotIn("month:'long'", R("index.html"))
        self.assertIn("{now:%b %Y}, {now:%H:%M}", R("scripts/stamp.py"))
        self.assertNotIn("'today, '", R("scripts/seo_meta.py")); self.assertNotIn("heddiw,", R("scripts/seo_meta.py"))
        self.assertNotIn("Updated today at", R("layers.js"))
    def test_policy_dates_automatic(self):
        import seo_meta
        d = json.load(open(os.path.join(ROOT, "overrides", "page_dates.json")))
        for p in ("privacy.html", "terms.html", "accessibility.html", "faq.html"):
            self.assertIn(p, d); self.assertIn("hash", d[p])
        s = '<p class="upd">Last updated 1 Jan 2000</p><p>x</p>'; dates = {}
        import datetime; from zoneinfo import ZoneInfo
        t = datetime.datetime(2026, 10, 25, 7, 30, tzinfo=ZoneInfo("Europe/London"))
        self.assertIn("Last updated 25 Oct 2026, 07:30", seo_meta.put_upd(s, "privacy.html", t, dates))
        t2 = datetime.datetime(2026, 11, 2, 9, 0, tzinfo=ZoneInfo("Europe/London"))
        self.assertIn("25 Oct 2026, 07:30", seo_meta.put_upd(s, "privacy.html", t2, dates))  # same text: date kept
        self.assertIn("2 Nov 2026, 09:00", seo_meta.put_upd(s.replace("x", "y"), "privacy.html", t2, dates))  # text changed: new date

    def test_every_rendered_date(self):
        """Every date a visitor can read is '25 Oct 2026, 05:12' (UK). A day with no clock time is '25 Oct 2026'.
        'Updated today at 05:55', long months, Welsh month names and ISO dates are not."""
        import html as html_mod
        mon = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
        ok = re.compile(rf"^(?:\d{{1,2}} (?:{mon}) \d{{4}})(?:, \d\d:\d\d)?$")
        timed = re.compile(rf"^\d{{1,2}} (?:{mon}) \d{{4}}, \d\d:\d\d$")
        find = re.compile(
            r"\b(?:today at \d\d:\d\d|today, \d\d:\d\d|heddiw, \d\d:\d\d|"
            r"\d{1,2} (?:January|February|March|April|June|July|August|September|October|November|December|"
            + mon + r"|Ionawr|Chwefror|Mawrth|Ebrill|Mehefin|Gorffennaf|Awst|Medi|Hydref|Tachwedd|Rhagfyr) \d{4}(?:, \d\d:\d\d)?|"
            r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?)\b")
        stamp_phrase = re.compile(
            r"(?:Information last updated|Map data last checked|Gwiriwyd data’r map ddiwethaf|Last updated|last updated|Updated) "
            r"(\d{1,2} \w+ \d{4}(?:, \d\d:\d\d)?)")
        bad = []
        pages = [os.path.join(ROOT, f) for f in ("index.html", "faq.html", "privacy.html", "terms.html", "accessibility.html", "404.html")]
        pages += glob.glob(os.path.join(ROOT, "*", "*", "index.html"))
        for p in pages:
            raw = open(p, encoding="utf-8").read()
            if "Updated today at" in raw or "'today, '" in raw or "heddiw," in raw:
                bad.append(os.path.relpath(p, ROOT) + ": relative 'today' date")
            vis = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.S | re.I)
            vis = re.sub(r"<style\b[^>]*>.*?</style>", " ", vis, flags=re.S | re.I)
            vis = html_mod.unescape(re.sub(r"<[^>]+>", " ", vis))
            for m in find.finditer(vis):
                if not ok.match(m.group(0)): bad.append("%s: %s" % (os.path.relpath(p, ROOT), m.group(0)))
            for m in stamp_phrase.finditer(vis):
                if not timed.match(m.group(1)): bad.append("%s: %s" % (os.path.relpath(p, ROOT), m.group(0)))
        self.assertFalse(bad, "\n".join(bad[:30]))

    def test_rendered_dates_in_the_browser(self):
        """Header, footer, key and a card use the same format, in English and in Welsh."""
        mon = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
        ok = re.compile(rf"^(?:\d{{1,2}} (?:{mon}) \d{{4}})(?:, \d\d:\d\d)?$")
        timed = re.compile(rf"^\d{{1,2}} (?:{mon}) \d{{4}}, \d\d:\d\d$")
        find = re.compile(
            r"\b(?:today at \d\d:\d\d|today, \d\d:\d\d|heddiw, \d\d:\d\d|"
            r"\d{1,2} (?:January|February|March|April|June|July|August|September|October|November|December|"
            + mon + r"|Ionawr|Chwefror|Mawrth|Ebrill|Mehefin|Gorffennaf|Awst|Medi|Hydref|Tachwedd|Rhagfyr) \d{4}(?:, \d\d:\d\d)?|"
            r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?)\b")
        stamp_phrase = re.compile(
            r"(?:Information last updated|Map data last checked|Gwiriwyd data’r map ddiwethaf|Last updated|last updated|Updated|Diweddarwyd) "
            r"(\d{1,2} \w+ \d{4}(?:, \d\d:\d\d)?)")
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        import functools, http.server, threading
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/index.html?nocount" % srv.server_address[1]
        shown = []
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block"); pg = c.new_page()
            pg.goto(url, wait_until="domcontentloaded"); pg.wait_for_timeout(1500)
            def grab():
                return pg.evaluate("""()=>{const t=s=>{const e=document.querySelector(s);return e?e.textContent:'';};
                  return [t('#freshtxt'),t('#upd'),t('#chk'),t('#u_fb'),t('#u_sh'),t('#u_ws'),
                    ...[...document.querySelectorAll('.src')].map(e=>e.textContent)] }""")
            pg.fill("#q", "BN17 5LF"); pg.press("#q", "Enter"); pg.wait_for_timeout(2000)
            shown += grab()
            pg.click("#xlang"); pg.wait_for_timeout(400)
            shown += grab()
            b.close()
        live = []
        for text in shown:
            for m in find.finditer(text or ""):
                if not ok.match(m.group(0)): live.append(m.group(0) + " in " + text[:80])
            for m in stamp_phrase.finditer(text or ""):
                if not timed.match(m.group(1)): live.append(m.group(0))
        self.assertTrue(any(timed.match(x.replace("Updated ", "").replace("updated ", "").replace("diweddarwyd ", "").strip()) or timed.search(x) for x in shown), shown[:6])
        self.assertFalse(any("today at" in (x or "") for x in shown), shown[:4])
        self.assertFalse(live, live[:20])

class Cards(unittest.TestCase):
    def test_hours_and_referral(self):
        l = R("layers.js"); v = R("v3.js")
        self.assertNotIn("Closed / not listed", l); self.assertIn("'Not listed'", l)
        self.assertIn("'Closed'", R("index.html"))
        self.assertIn("By referral – call before you go", v); self.assertIn("REFONLY(i)?''", l)
    def test_shelter_credits(self):
        s = R("404.html")
        self.assertIn("for shelters", s); self.assertIn("Homeless Link", s)

if __name__ == "__main__": unittest.main()
