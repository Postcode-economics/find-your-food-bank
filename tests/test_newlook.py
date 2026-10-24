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
