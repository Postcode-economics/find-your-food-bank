"""Motion Designer live QA round 3 (28 Oct 2026): F1, F3, M1, M2, M3. F2 (Heston Farm) is on Dean's review list, not code.

Same harness as test_phone_qa_28oct: Chromium phone, iPhone WebKit with the backup map off, and with it forced on.
Nothing real leaves the browser (site files served from this checkout, tiles and postcodes stubbed).
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_phone_qa_28oct import PhoneQA, until
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SANDBACH = "items.findIndex(i=>/^Sandbach Foodbank$/i.test(i.name)&&!i.phone&&i.fb_page)"


class MotionRound3(PhoneQA):
    # PhoneQA's own tests are not re-run from here
    test_b1_nearest_list_follows_type = test_b2_bad_postcode_clears_results_and_says_so = None
    test_b4_filter_close_not_alone_at_375_dark = test_b6_tap_targets = test_b7_tel_links_have_names = None

    def wide(self, opts, w, h):
        o = dict(opts); o["viewport"] = {"width": w, "height": h}
        o.pop("is_mobile", None); o["has_touch"] = True
        return o

    def test_f1_f3_sheet_facebook_button_no_logo_above_the_fold(self):
        for name, b, opts in self.engines():
            for light in (False, True):
                c, pg = self.page(b, opts, light=light)
                k = pg.evaluate(SANDBACH)
                self.assertGreaterEqual(k, 0, name)
                pg.evaluate(f"select({k},true)"); pg.wait_for_timeout(1200)
                until(pg, "document.getElementById('sheet').classList.contains('open')")
                r = pg.evaluate("""()=>{const s=document.getElementById('sheet'),a=s.querySelector('#sheetBody a.btn.call.xfbk');if(!a)return null;
                  const p=a.previousElementSibling,ab=a.getBoundingClientRect(),sb=s.getBoundingClientRect();
                  return {prev:p&&p.className,logo:!!a.querySelector('img,svg'),txt:a.textContent.trim(),
                    bottom:ab.bottom,sheetBottom:Math.min(sb.bottom,innerHeight),h:ab.height,scroll:document.getElementById('sheetBody').scrollTop}}""")
                self.assertIsNotNone(r, name)
                self.assertFalse(r["logo"], (name, light, r))                   # F1
                self.assertEqual(r["txt"], "Send a message", (name, r))
                self.assertIn("gm", r["prev"], (name, light, r))                 # F3: straight after Directions
                self.assertEqual(r["scroll"], 0, (name, r))
                self.assertLessEqual(r["bottom"], r["sheetBottom"], (name, light, r))  # visible without scrolling
                self.assertGreaterEqual(r["h"], 44, (name, r))
                c.close()

    def test_f1_list_card_no_logo(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            k = pg.evaluate(SANDBACH)
            pg.evaluate(f"(()=>{{const i=items[{k}];nearest(i.lat,i.lng,i.postcode)}})()"); pg.wait_for_timeout(1500)
            r = pg.evaluate("[...document.querySelectorAll('#list a.btn.call.xfbk')].map(a=>[a.textContent.trim(),!!a.querySelector('img,svg')])")
            self.assertTrue(r, name)
            for txt, logo in r:
                self.assertEqual(txt, "Send a message", name); self.assertFalse(logo, name)
            c.close()

    def test_m1_one_filter_row_wide(self):
        for name, b, opts in self.engines():
            for w, h in ((768, 1024), (1280, 800)):
                for light in (False, True):
                    c, pg = self.page(b, self.wide(opts, w, h), light=light)
                    r = pg.evaluate("""()=>{const g=id=>document.getElementById(id).getBoundingClientRect();const x=g('fhide'),o=g('v3open'),t=g('v3tools');
                        return {xt:x.top,ot:o.top,tt:t.top,gap:x.left-o.right,tl:t.left,xr:x.right,vw:innerWidth,sw:document.documentElement.scrollWidth}}""")
                    self.assertLess(abs(r["xt"] - r["ot"]), 4, (name, w, r))      # ✕ on the 'Open today only' row
                    self.assertLess(r["gap"], 24, (name, w, r))                    # right after it, not at the far edge
                    self.assertLess(abs(r["tt"] - r["ot"]), 4, (name, w, r))      # List only / Light mode on the same row
                    self.assertGreater(r["tl"], r["xr"], (name, w, r))
                    self.assertLessEqual(r["sw"], r["vw"], (name, w, r))
                    c.close()

    def test_m2_popup_close_44px(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, self.wide(opts, 1280, 800))
            k = pg.evaluate(SANDBACH)
            pg.evaluate(f"L.popup().setLatLng([items[{k}].lat,items[{k}].lng]).setContent(pop(items[{k}])).openOn(map)"); pg.wait_for_timeout(800)
            r = pg.evaluate("""()=>{const x=document.querySelector('.leaflet-popup-close-button');if(!x)return null;const b=x.getBoundingClientRect(),
                h=document.querySelector('.leaflet-popup-content h3').getBoundingClientRect();return {w:b.width,h:b.height,overlap:h.right>b.left&&h.top<b.bottom}}""")
            self.assertIsNotNone(r, name)
            self.assertGreaterEqual(r["w"], 44, (name, r)); self.assertGreaterEqual(r["h"], 44, (name, r))
            self.assertFalse(r["overlap"], (name, r))
            pg.click(".leaflet-popup-close-button"); pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("document.querySelectorAll('.leaflet-popup').length"), 0, name)
            c.close()

    def test_m3_light_mode_carries_to_faq_and_legal_pages(self):
        for name, b, opts in self.engines():
            for w, h in ((375, 812), (1280, 800)):
                for light in (True, False):
                    c, pg = self.page(b, self.wide(opts, w, h) if w > 400 else opts, light=light)
                    for page in ("/faq.html", "/privacy.html", "/terms.html", "/accessibility.html"):
                        pg.goto(self.BASE_URL + page, wait_until="load"); pg.wait_for_timeout(300)
                        r = pg.evaluate("()=>({cls:document.documentElement.classList.contains('light'),bg:getComputedStyle(document.body).backgroundColor})")
                        self.assertEqual(r["cls"], light, (name, page, r))
                        self.assertEqual(r["bg"], "rgb(255, 255, 255)" if light else "rgb(10, 22, 40)", (name, w, page, r))
                    c.close()

    BASE_URL = "https://helpmap.uk"


class StaticRound3(unittest.TestCase):
    def test_static_pages_follow_saved_choice_not_os(self):
        for f in ("faq.html", "privacy.html", "terms.html", "accessibility.html"):
            s = open(os.path.join(ROOT, f), encoding="utf-8").read()
            self.assertNotIn("prefers-color-scheme:light", s, f)   # first visit stays dark (Dean 25 Oct)
            self.assertIn("localStorage.getItem('light')==='1'", s[:s.index("<style>")], f)


if __name__ == "__main__":
    unittest.main()
