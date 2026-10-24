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
