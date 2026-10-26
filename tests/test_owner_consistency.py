"""owner's consistency decisions (25 Oct 2026, 07:48): 'call before you go' everywhere; one date format
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
        self.assertIn("month:'short'", R("index.html")); self.assertNotIn("month:'long'", R("index.html"))
        self.assertIn("{now:%b %Y}, {now:%H:%M}", R("scripts/stamp.py"))
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
