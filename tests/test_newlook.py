"""New look (Dean's mockups 24 Oct): ported from Motion Designer's design source (siteD = call button, siteFB = Facebook button)."""
import os, re, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
rd = lambda f: open(os.path.join(ROOT, f), encoding="utf-8").read()

class NewLook(unittest.TestCase):
    def test_tokens(self):
        css = rd("v3.css"); html = rd("index.html")
        for v in ("#0A1628", "#13223d", "#34C759", "#1877F2", "#C9A96E", "#8A6A2E", "#00D1FF", "#00739E", "#D55E00", "#FF3B30"):
            self.assertIn(v.lower(), (css + html).lower(), v)
    def test_no_faded_cards(self):  # Dean: full-strength colours on every card, closed ones too
        css = rd("v3.css")
        self.assertTrue("html body .card.v3closed>*,html body .card.v3closed{opacity:1!important" in css, "closed cards must be reset to full opacity")
    def test_facebook_only_without_phone(self):  # Dean 14:50: phone wins; Facebook only when no phone
        html = rd("index.html")
        i = html.index('!tel&&i.fb_page?`<a class="btn call xfbk"')
        self.assertIn('href="${esc(i.fb_page)}"', html[i:i + 300])
        self.assertIn("Send a message", html[i:i + 400])
        self.assertTrue(os.path.exists(os.path.join(ROOT, "fb_secondary.png")))
    def test_tag_wording(self):
        self.assertIn("[/^Food bank$/,'Banc bwyd']", rd("layers.js"))
    def test_review_1625(self):  # Dean 16:25: wider card gap, FB label = Directions size, centred logo+label
        css = rd("v3.css")
        self.assertIn("html body #xextra #xlist>.card,html body #list>.card{margin-bottom:26px!important}", css)
        self.assertIn("a.btn.call.xfbk span{font-size:16px!important;font-weight:800!important", css)
        self.assertIn("justify-content:center!important;gap:8px!important;padding:0 12px!important", css)
    def test_no_venue_number_sentence_only_without_phone(self):  # Dean 16:40
        self.assertIn(":tel?'':`<p class=\"sub\">${cy?'Dim rhif i’r lle ei hun.", rd("layers.js"))
    def test_call_buttons_16_800(self):  # Dean 16:51
        css = rd("v3.css")
        self.assertIn("a.btn.call:not(.xfbk) *:not(svg):not(path){font-size:16px!important;font-weight:800!important", css)
        self.assertIn(".xnum,html body #list .card>a.btn.call:not(.xfbk) .xnum", css)
    def test_call_type_identical_to_directions(self):  # Dean 17:10
        css = rd("v3.css")
        self.assertIn("html body .card a.btn.gm{letter-spacing:normal!important;transform:none!important", css)
        self.assertIn("html body .card a.btn.cdir{font-size:16px!important;font-weight:800!important", css)
        self.assertIn(":has(>small){flex-wrap:wrap!important;min-width:0!important;max-width:100%!important", css)
    def test_council_button_two_centred_lines(self):  # Dean 17:33
        js = rd("layers.js"); css = rd("v3.css")
        self.assertEqual(js.count('<a class="btn call xfb"'), js.count('<span class="xcl">'))
        self.assertEqual(js.count('<span class="xcl">'), js.count('<span class="xcn">${IC(\'phone\')}'))
        self.assertIn("a.btn.call.xfb{display:flex!important;flex-direction:column!important", css)
    def test_sheet_body_scrolls_header_fixed(self):  # Dean 19:02 iPhone: content must not slide behind the sheet header
        css = rd("v3.css"); html = rd("index.html")
        self.assertIn("#sheet{display:flex!important;flex-direction:column!important;overflow:hidden!important", css)
        self.assertIn("#sheet>#sheetBody{flex:1 1 auto!important;min-height:0!important;overflow-y:auto!important", css)
        self.assertIn("$('sheetBody').scrollTop>0", html)
    def test_green_call_button_dark_handset(self):  # Dean 21:25 'lock in the new format'
        css = rd("v3.css")
        self.assertIn("html body #list .card a.btn.call,html body #xextra .card a.btn.call{background:#34C759!important;border-color:#34C759!important;color:#000!important}", css)
        self.assertIn("html body #list .card a.btn.call svg.ico,html body #list .card a.btn.call svg.ico *,html body #xextra .card a.btn.call svg.ico,html body #xextra .card a.btn.call svg.ico *{color:#2B2B2B!important;fill:#2B2B2B!important", css)
    def test_facebook_blue_with_logo(self):
        css = rd("v3.css"); html = rd("index.html")
        self.assertIn("html body #list .card a.btn.call.xfbk,html body #xextra .card a.btn.call.xfbk{background:#1877F2!important;border-color:#1877F2!important;color:#fff!important", css)
        self.assertIn("a.btn.call.xfbk img.fboff{width:20px!important;height:20px!important", css)
        # Motion QA 28 Oct F1 (Dean): no Facebook brand logo on "Send a message".
        i = html.index('!tel&&i.fb_page?`<a class="btn call xfbk"'); j = html.index('</a>', i)
        self.assertNotIn("<img", html[i:j]); self.assertNotIn("fb_secondary", html[i:j]); self.assertNotIn("<svg", html[i:j])


class NewLookRendered(unittest.TestCase):
    """Real index.html + v3.css + data.js in Chromium (tests/newlook_render.py), cards in #list as live."""
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest("playwright not available: %s" % e)
        cls.R = R; cls.pw = sync_playwright().start()
        try: cls.b, cls.p = R.open_page(cls.pw, 'dark')
        except Exception as e:
            cls.pw.stop(); raise unittest.SkipTest("no browser: %s" % e)
    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop()
    def test_rendered_phone_card_green(self):
        c = self.R.show_in_list(self.p, 'selkirk'); self.assertIsNotNone(c)
        s = c.evaluate("""c=>{const a=c.querySelector('a.btn.call:not(.xfbk)'),t=a.querySelector('*:not(svg):not(path)')||a,i=a.querySelector('svg.ico'),g=getComputedStyle;
          return {bg:g(a).backgroundColor,fs:g(t).fontSize,fw:g(t).fontWeight,icon:g(i).fill,mb:g(c).marginBottom,fb:!!c.querySelector('.xfbk')}}""")
        self.assertEqual(s, {'bg': 'rgb(52, 199, 89)', 'fs': '16px', 'fw': '800', 'icon': 'rgb(43, 43, 43)', 'mb': '26px', 'fb': False})
    def test_rendered_facebook_card_blue(self):
        # Whitland now has the shared venue phone (Dean, 26 Oct), so its card is a call button.
        # Sandbach still has no phone and a verified Facebook page, so this stays the blue Message button.
        c = self.R.show_in_list(self.p, 'sandbach'); self.assertIsNotNone(c)
        s = c.evaluate("""c=>{const a=c.querySelector('a.btn.call.xfbk'),g=getComputedStyle;return {bg:g(a).backgroundColor,jc:g(a).justifyContent,
          logo:!!a.querySelector('img,svg'),txt:a.textContent.trim(),fs:g(a.querySelector('span')).fontSize,fw:g(a.querySelector('span')).fontWeight}}""")
        self.assertEqual(s, {'bg': 'rgb(24, 119, 242)', 'jc': 'center', 'logo': False, 'txt': 'Send a message', 'fs': '16px', 'fw': '800'})
    def test_rendered_sheet_only_body_scrolls(self):
        s = self.p.evaluate("()=>({sheet:getComputedStyle(document.getElementById('sheet')).overflowY,body:getComputedStyle(document.getElementById('sheetBody')).overflowY})")
        self.assertEqual(s, {'sheet': 'hidden', 'body': 'auto'})


class SheetGreen(unittest.TestCase):  # Dean 24 Oct 21:31: sheet cards = same green call / blue Facebook as #list
    def test_static_sheet_rules(self):
        css = rd("v3.css")
        self.assertIn("html body #sheetBody .card a.btn.call{background:#34C759!important;border-color:#34C759!important;color:#000!important}", css)
        self.assertIn("html body #sheetBody .card a.btn.call svg.ico,html body #sheetBody .card a.btn.call svg.ico *{color:#2B2B2B!important;fill:#2B2B2B!important", css)
        self.assertIn("html body #sheetBody .card a.btn.call.xfbk{background:#1877F2!important", css)
    def test_rendered_sheet_from_pin(self):
        try:
            from playwright.sync_api import sync_playwright
            import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest("playwright not available: %s" % e)
        with sync_playwright() as pw:
            try: b, p = R.open_page(pw, 'light')
            except Exception as e: raise unittest.SkipTest("no browser: %s" % e)
            try:
                out = {}
                for fid in ('selkirk', 'sandbach'):
                    p.evaluate("id=>{const k=items.findIndex(x=>x.id===id);map.setView(markers[k].getLatLng(),16);markers[k].fire('click')}", fid)
                    p.wait_for_timeout(700)
                    out[fid] = p.evaluate("""()=>{const a=document.querySelector('#sheetBody .card a.btn.call'),i=a.querySelector('svg.ico');
                      return [getComputedStyle(a).backgroundColor,i?getComputedStyle(i).fill:null]}""")
                self.assertEqual(out['selkirk'], ['rgb(52, 199, 89)', 'rgb(43, 43, 43)'])
                self.assertEqual(out['sandbach'][0], 'rgb(24, 119, 242)')
            finally: b.close()


class HelplineBoxNotInCards(unittest.TestCase):
    """Dean 24 Oct: the 'Sleeping rough… StreetLink / Call 999' box shows ONCE, above the list (#v3sos), never inside a card or the sheet."""
    def test_card_template_has_no_strip(self):
        s = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'layers.js'), encoding='utf-8').read()
        self.assertNotIn('V3.strip()', s)
    def test_rendered_shelters_box_only_on_top(self):
        try:
            from playwright.sync_api import sync_playwright
            import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest("playwright not available: %s" % e)
        with sync_playwright() as pw:
            b, p = R.open_page(pw, 'dark')
            try:
                p.click('.v3b[data-l=sh]'); p.wait_for_timeout(1200)
                p.evaluate("()=>nearest(50.797102,-1.0773661,'PO1 1PT')"); p.wait_for_timeout(2000)
                p.evaluate("()=>{const c=document.querySelector('#xlist .card.xsh');if(c)c.click()}"); p.wait_for_timeout(800)
                s = p.evaluate("""()=>({cards:document.querySelectorAll('#xlist .card.xsh').length,
                  top:document.querySelectorAll('#v3sos .v3sos').length,topShown:!document.getElementById('v3sos').hidden,
                  stray:[...document.querySelectorAll('.v3sos')].filter(e=>!e.closest('#v3sos')).length})""")
            finally:
                b.close()
        self.assertGreater(s['cards'], 0)
        self.assertEqual(s, {'cards': s['cards'], 'top': 1, 'topShown': True, 'stray': 0})
