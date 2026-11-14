"""14 Nov 2026 (Dean): the yellow Find nearest bar must sit at the same top on Food banks,
Warm spaces and Shelter at phone sizes, and the unapproved 'Food banks near you' text
under the bar must not show (idle or after a search / last-near restore)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_showmore_layers import serve, prepare, HAVE_CHROME
from site_ready import open_map

ROOT = os.path.join(os.path.dirname(__file__), '..')
CH = '/usr/bin/google-chrome'

READY = """() => {
  const f=document.getElementById('v3filt'), b=document.getElementById('h2bar'), n=document.getElementById('xnear');
  return !!(f && b && n && getComputedStyle(n).display!=='none' && n.getBoundingClientRect().height>1);
}"""

MEAS = r"""() => {
  const g = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return {t:r.top, b:r.bottom, h:r.height, l:r.left, r:r.right, w:r.width}; };
  const vis = e => !!(e && e.offsetParent && getComputedStyle(e).display!=='none' && e.getBoundingClientRect().height>1);
  const filt = document.getElementById('v3filt');
  const chips = [...(filt ? filt.querySelectorAll('.fchip, #v3open, #fhide') : [])]
    .filter(e => vis(e)).map(e => { const r=e.getBoundingClientRect(); return {id:e.id||e.getAttribute('data-f')||e.className, t:r.top, b:r.bottom, h:r.height, text:(e.innerText||'').trim()}; });
  const prow=document.getElementById('v3prow'), pl=document.querySelector('#v3pill .v3pl');
  return {k: document.documentElement.dataset.v3k, lang: document.documentElement.lang,
    filt: g(filt), near: g(document.getElementById('xnear')), bar: g(document.getElementById('h2bar')),
    prowOn: vis(prow), plOn: vis(pl), plText: (pl && vis(pl) && (pl.innerText||'').trim()) || '',
    chips};
}"""


def until(pg, expr, seconds=20):
    for _ in range(int(seconds * 5)):
        try:
            if pg.evaluate(expr):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(200)
    return False


@unittest.skipUnless(HAVE_CHROME, 'needs chrome + playwright')
class FindNearestBar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.srv, cls.base = serve()
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.chromium.launch(executable_path=CH)

    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop(); cls.srv.shutdown()

    def _page(self, w, lang='en'):
        kw = dict(viewport={'width': w, 'height': 844}, service_workers='block')
        if w < 800:
            kw.update(is_mobile=True, has_touch=True)
        c = self.b.new_context(**kw)
        # start on food banks; do not wait for every layer script
        prepare(c, 'fb')
        self.addCleanup(c.close)
        pg = c.new_page()
        open_map(pg, self.base + '/?nocount')
        self.assertTrue(until(pg, READY, 25), 'header not ready')
        if lang == 'cy':
            pg.click('#xlang')
            self.assertTrue(until(pg, "() => document.documentElement.lang === 'cy'", 8))
        return pg

    def _layer(self, pg, k):
        pg.evaluate("k=>{const t=document.querySelector('#v3big [data-l='+k+']');if(t)t.click()}", k)
        self.assertTrue(until(pg, "() => document.documentElement.dataset.v3k === %r" % k, 8))
        self.assertTrue(until(pg, READY, 10))
        pg.evaluate('scrollTo(0,0)')
        pg.wait_for_timeout(200)

    def test_bar_top_matches_and_place_line_hidden(self):
        for lang in ('en', 'cy'):
            for w in (390, 360, 320):
                with self.subTest(lang=lang, w=w):
                    pg = self._page(w, lang)
                    tops, filts, rows = {}, {}, {}
                    for k in ('fb', 'ws', 'sh'):
                        self._layer(pg, k)
                        m = pg.evaluate(MEAS)
                        self.assertIsNotNone(m['near'], (lang, w, k, 'Find nearest bar missing', m))
                        self.assertFalse(m['prowOn'] or m['plOn'], (lang, w, k, 'place line visible idle', m))
                        self.assertGreaterEqual(len(m['chips']), 3, (lang, w, k, m['chips']))
                        for ch in m['chips']:
                            self.assertGreaterEqual(ch['h'], 32, (lang, w, k, 'chip too short', ch))
                            self.assertTrue(ch['text'], (lang, w, k, 'empty chip', ch))
                        tops[k] = m['near']['t']
                        filts[k] = m['filt']['h']
                    self.assertLess(abs(tops['fb'] - tops['ws']), 1, (lang, w, tops, filts))
                    self.assertLess(abs(tops['fb'] - tops['sh']), 1, (lang, w, tops, filts))
                    self.assertLess(abs(filts['fb'] - filts['sh']), 1, (lang, w, 'filter height mismatch', filts))

    def test_place_line_stays_hidden_after_search_and_last_near(self):
        pg = self._page(390, 'en')
        pg.fill('#q', 'M1 1AE')
        pg.press('#q', 'Enter')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#list .card').length > 0", 15))
        m = pg.evaluate(MEAS)
        self.assertFalse(m['prowOn'] or m['plOn'], ('after search', m))
        # restore as a phone would after lastNear / lastSearch
        pg.evaluate("""() => { try {
          localStorage.setItem('lastNear', JSON.stringify({lat:53.48,lng:-2.24,label:'Manchester'}));
          localStorage.setItem('lastSearch', JSON.stringify({lat:53.48,lng:-2.24,label:'Manchester'}));
        } catch(e) {} }""")
        pg.reload(wait_until='load')
        self.assertTrue(until(pg, READY, 25))
        # give any restore a moment
        pg.wait_for_timeout(1500)
        m = pg.evaluate(MEAS)
        self.assertFalse(m['prowOn'] or m['plOn'], ('after lastNear restore', m))


if __name__ == '__main__':
    unittest.main()
