import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_seo as B
ROOT = os.path.join(os.path.dirname(__file__), '..')
class T(unittest.TestCase):
    def test_public_rule(self):
        base = dict(name='x', postcode='N3 1TR', source='Homeless Link')
        self.assertTrue(B.shelter_public(base))
        self.assertFalse(B.shelter_public(dict(base, stale=True)))
        self.assertFalse(B.shelter_public(dict(base, ended=True)))
        self.assertFalse(B.shelter_public(dict(base, flag_closed=True)))
        self.assertFalse(B.shelter_public(dict(base, source='OpenStreetMap')))
        self.assertTrue(B.shelter_public(dict(base, source='OpenStreetMap', evidence_url='https://a')))
    def test_card(self):
        c = B.card_sh(dict(name='Barnet WNS', address='N3 1TR', postcode='N3 1TR', tier='unverified', access_type='referral_only',
                           referral='Via HAB', upcoming=True, scheme_start='2026-11-08', scheme_dates='Opens 8 Nov 2026', hours=''))
        for s in ('Referral only', 'Via HAB', 'You need a referral', '<div class="opens">Opens 8 Nov 2026</div>', 'Unverified – call before you go', 'faq.html#times'):
            self.assertIn(s, c)
    def test_ws_card(self):
        c = B.card_ws(dict(name='W', address='a', upcoming=True, scheme_start='2026-11-04', scheme_dates='Opens 4 Nov 2026', booking='Booking needed', notes='By referral from GP', hours={}))
        self.assertIn('<div class="opens">Opens 4 Nov 2026</div>', c); self.assertIn('Booking needed', c); self.assertIn('Referral:', c)
        self.assertIn('Times unknown – call first', B.card_ws(dict(name='W', address='a', call_check=True, hours={})))
    def test_built_pages(self):   # the committed pages: meta, line, cross-links, sitemap
        p = open(os.path.join(ROOT, 'shelters', 'barnet', 'index.html')).read()
        self.assertIn('Checked three times a day.', p); self.assertIn('class="mapchk"', p); self.assertIn('Checked three times daily', p)
        self.assertIn('href="/food-banks/barnet/"', p); self.assertIn('"dateModified"', p)
        self.assertIn('https://helpmap.uk/shelters/barnet/', open(os.path.join(ROOT, 'sitemap.xml')).read())
        self.assertNotIn('<!--xlinks', p)
