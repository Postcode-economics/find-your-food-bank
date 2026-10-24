"""UK number display grouping (Dean 24 Oct 21:31): ukfmt in index.html, used by the call-button rewriter in layers.js. Display only."""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read()
CASES = {'01618172250': '0161 817 2250', '01314423304': '0131 442 3304', '01132623233': '0113 262 3233', '01214712379': '0121 471 2379',
         '01412345678': '0141 234 5678', '01517778451': '0151 777 8451', '01142345678': '0114 234 5678', '01159222050': '0115 922 2050',
         '01162345678': '0116 234 5678', '01179551600': '0117 955 1600', '01189123456': '0118 912 3456', '02087882024': '020 8788 2024',
         '02890123456': '028 9012 3456', '02920123456': '029 2012 3456', '02392825673': '023 9282 5673', '02476123456': '024 7612 3456',
         '01670620015': '01670 620015', '07517747501': '07517 747501', '03001240204': '0300 124 0204', '08001234567': '0800 123 4567',
         '03451234567': '0345 123 4567', '0161 817 2250': '0161 817 2250', '015394 12345': '015394 12345', '01460 57811': '01460 57811',
         'not a number': 'not a number'}

class PhoneFormat(unittest.TestCase):
    def test_static(self):
        self.assertIn("function ukfmt(v)", rd("index.html"))
        self.assertIn("if(window.ukfmt)return ukfmt(d);", rd("layers.js"))
        self.assertIn('href="tel:${esc(tel)}"', rd("index.html"))  # tel: links unchanged
    def test_rendered(self):
        try:
            from playwright.sync_api import sync_playwright
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import newlook_render as R
        except Exception as e: raise unittest.SkipTest(str(e))
        with sync_playwright() as pw:
            try: b, p = R.open_page(pw)
            except Exception as e: raise unittest.SkipTest(str(e))
            try:
                got = p.evaluate("c=>Object.fromEntries(Object.keys(c).map(k=>[k,ukfmt(k)]))", CASES)
                self.assertEqual(got, CASES)
                c = R.show_in_list(p, 'ifan-5b3e01fe979d373d9ba679-0')
                a = c.query_selector('a.btn.call')
                self.assertEqual(a.inner_text().strip(), '0161 817 2250'); self.assertEqual(a.get_attribute('href'), 'tel:01618172250')
            finally: b.close()
