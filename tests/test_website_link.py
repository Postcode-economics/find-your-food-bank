"""Website button only for a real http(s) URL (28 Oct 2026, batch 1).

layers.js used to prefix any website value with https://, so free text became a link such as
https://We do not have a website or https://undefined. Same harness as test_phone_qa_28oct: Chromium phone,
iPhone WebKit with the backup map off, and with it forced on; nothing real leaves the browser.
"""
import os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_phone_qa_28oct import PhoneQA, until
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

BAD = ["We do not have a website", "undefined", "null", "", "   ", "www.example.org", "example.org",
       "https://We do not have a website", "https://undefined", "http://", "https://", "ftp://example.org",
       "javascript:alert(1)", "mailto:info@example.org", "https://example .org", "Facebook page only"]
GOOD = ["https://www.example.org/foodbank", "http://example.org", "https://example.org.uk/a?b=1#c",
        "  https://www.example-trust.org.uk/  "]


class Source(unittest.TestCase):
    def test_no_https_prefix_on_free_text(self):
        js = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()
        html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertNotIn("'https://'+i.website", js.split("function detail(")[0])
        self.assertRegex(js, r"const w=webUrl\(i\.website\);\s*if\(w\)o\.push\(`<a class=\"btn web\"")
        self.assertIn("const webUrl=", html)  # in the boot script: cards render before layers.js runs
        self.assertIn("const site=i=>web(i)||i.givefood;", html)
        self.assertNotIn("i.website||", html)


class WebsiteLink(PhoneQA):
    # PhoneQA's own tests are not re-run from here
    test_b1_nearest_list_follows_type = test_b2_bad_postcode_clears_results_and_says_so = None
    test_b4_filter_close_not_alone_at_375_dark = test_b6_tap_targets = test_b7_tel_links_have_names = None

    def test_web_url_accepts_only_http_urls(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            got = pg.evaluate("vs => vs.map(v => !!webUrl(v))", BAD + GOOD + [None, 42])
            self.assertEqual(got, [False] * len(BAD) + [True] * len(GOOD) + [False, False], name)
            c.close()

    def test_food_bank_sheet_links_only_a_real_url(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            k = pg.evaluate("items.findIndex(i => /^https:\\/\\//.test(i.website || '') && i.givefood && !i.source_label)")
            self.assertGreaterEqual(k, 0, name)
            gf = pg.evaluate("k => items[k].givefood", k)
            for value in BAD + GOOD:
                pg.evaluate("([k, v]) => { items[k].website = v; select(k, true) }", [k, value])
                until(pg, "document.getElementById('sheet').classList.contains('open')")
                pg.wait_for_timeout(150)
                theirs = pg.evaluate("""() => [...document.querySelectorAll('#sheetBody .links a')]
                    .filter(a => a.textContent.trim() === 'Their website').map(a => a.getAttribute('href'))""")
                # No real site: "Their website" falls back to the Give Food page, as it did for an empty field.
                self.assertEqual(theirs, [value.strip() if value in GOOD else gf], (name, value))
                html = pg.evaluate("() => document.getElementById('sheetBody').innerHTML")
                self.assertNotRegex(html, r'href="(https?://)?(We do|undefined|null|Facebook)', (name, value))
            c.close()

    def test_shelter_and_warm_space_cards_website_button_only_for_a_real_url(self):
        """Shelter / warm space cards (layers.js detail -> shContact) carry the Website button."""
        values = [v for pair in zip(GOOD * 4, BAD) for v in pair]  # good, bad, good, bad: even 3 cards hold both
        for name, b, opts in self.engines():
            for k, cls_, var in (("sh", "xsh", "SHELTERS"), ("ws", "xws", "WARMSPACES")):
                c, pg = self.page(b, opts)
                pg.click(f".v3b[data-l={k}]")
                until(pg, f"!!(window.{var} && {var}.items && {var}.items.length)")
                # The listings nearest M1 1AE get the test values in turn, so the result cards mix bad and good ones.
                given = pg.evaluate("""([v, vals]) => { const near = window[v].items.filter(i => i.lat != null && i.lng != null)
                    .map(i => [Math.hypot(i.lat - 53.4794, (i.lng + 2.2453) * 0.6), i]).sort((a, b) => a[0] - b[0]).slice(0, 60);
                    const out = {}; near.forEach(([d, i], n) => { i.website = vals[n % vals.length]; out[i.name] = i.website }); return out }""",
                    [var, values])
                self.search(pg, "M1 1AE")
                until(pg, f"document.querySelectorAll('#xlist .card.{cls_}').length>0")
                cards = pg.evaluate(f"""() => [...document.querySelectorAll('#xlist .card.{cls_}')].map(e => ({{
                    name: (e.querySelector('h3') || {{}}).textContent || '',
                    web: [...e.querySelectorAll('a.btn.web')].map(a => [a.getAttribute('href'), (a.querySelector('.xdom') || {{}}).textContent || ''])}}))""")
                seen = {"good": 0, "bad": 0}
                for card in cards:
                    if card["name"] not in given:
                        continue
                    value = given[card["name"]]
                    if value in GOOD:
                        host = re.sub(r"^www\.", "", value.strip().split("/")[2].split("?")[0])
                        self.assertEqual(card["web"], [[value.strip(), host]], (name, k, card))
                        seen["good"] += 1
                    else:
                        self.assertEqual(card["web"], [], (name, k, value, card))
                        seen["bad"] += 1
                self.assertTrue(seen["good"] and seen["bad"], (name, k, seen, len(cards)))
                c.close()


if __name__ == "__main__":
    unittest.main()
