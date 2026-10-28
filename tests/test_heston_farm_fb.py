"""Heston Farm Foodbank (heston-farm, TW5 0EE): its Facebook group was only in `website`, so the card's
standard Facebook button never showed. fb_page now comes from overrides/facebook_pages.json (Dean 28 Oct 08:15)."""
import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
URL = "https://www.facebook.com/groups/940970613570584"


def rd(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()
def item(path):
    s = rd(path); d = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))
    return next(i for i in (d["items"] if isinstance(d, dict) else d) if i["id"] == "heston-farm")


class HestonFarmFacebook(unittest.TestCase):
    def test_override_survives_refresh(self):
        e = json.loads(rd("overrides/facebook_pages.json"))["heston-farm"]
        self.assertEqual(e["url"], URL); self.assertTrue(e["page_title"])
        self.assertIn("if i['id'] in fbp: i['fb_page'] = fbp[i['id']]['url']", rd("scripts/build.py"))

    def test_data_has_fb_page_and_no_phone(self):
        i = item("data.full.js")
        self.assertEqual(i.get("fb_page"), URL); self.assertFalse(i.get("phone") or i.get("tel"))
        self.assertEqual(i["postcode"], "TW5 0EE")
        self.assertIn(json.dumps(URL), rd("data.js"))

    def test_undo_logged(self):
        e = [c for c in json.loads(rd("logs/listings_batch_28oct.json"))["changes"] if c["id"] == "heston-farm" and c["field"] == "fb_page"]
        self.assertEqual(len(e), 1); self.assertEqual(e[0]["new"], URL); self.assertEqual(e[0]["source"], URL)
        self.assertEqual(e[0]["undo"]["set"], {"fb_page": None})


class HestonFarmRendered(unittest.TestCase):
    """Real index.html + v3.css + data.js in Chromium (tests/newlook_render.py)."""
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest("playwright not available: %s" % e)
        cls.R = R; cls.pw = sync_playwright().start()
        try: cls.b, cls.p = R.open_page(cls.pw, 'light')
        except Exception as e:
            cls.pw.stop(); raise unittest.SkipTest("no browser: %s" % e)
    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop()

    def btn(self, fid):
        c = self.R.show_in_list(self.p, fid); self.assertIsNotNone(c, fid)
        return c.evaluate("""c=>{const a=c.querySelector('a.btn.call.xfbk');return a?{href:a.getAttribute('href'),txt:a.textContent.trim(),
          aria:a.getAttribute('aria-label'),bg:getComputedStyle(a).backgroundColor,html:a.outerHTML.replace(a.getAttribute('href'),'URL'),
          calls:c.querySelectorAll('a.btn.call:not(.xfbk)').length}:null}""")

    def test_card_renders_standard_facebook_button(self):
        s = self.btn('heston-farm'); self.assertIsNotNone(s)
        self.assertEqual((s['href'], s['txt'], s['aria'], s['calls']), (URL, 'Send a message', 'Send a message on Facebook', 0))
        ref = self.btn('sandbach')  # an existing no-phone card with a verified page: same generic button
        self.assertEqual({k: s[k] for k in ('html', 'bg', 'txt')}, {k: ref[k] for k in ('html', 'bg', 'txt')})


if __name__ == "__main__": unittest.main()
