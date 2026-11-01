"""Shelter type chips (Dean): Hostel or shelter, Young people, Day centre.

Food-bank chips hide on Shelter and come back on Food bank. At 390px and at 320px
the reset shares a row with Day centre and Open today. None pressed shows every
type; one or more chips keep the list, the map and Show more to those types.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_showmore_layers import serve, prepare, open_page, until, HAVE_CHROME

ROOT = os.path.join(os.path.dirname(__file__), '..')
CH = '/usr/bin/google-chrome'

LAYOUT = r"""() => {
  const g = sel => { const e = document.querySelector(sel); if (!e) return null;
    const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return {t: r.top, l: r.left, r: r.right, b: r.bottom, w: r.width, h: r.height, show: s.display !== 'none' && r.width > 0}; };
  const svg = document.querySelector('#chips [data-f=shost] svg');
  const sr = svg && svg.getBoundingClientRect();
  const ck = document.querySelector('#chips [data-f=shost] .ck');
  const cr = ck && ck.getBoundingClientRect();
  return {vw: innerWidth, sw: document.documentElement.scrollWidth,
    host: g('#chips [data-f=shost]'), youth: g('#chips [data-f=youth]'), day: g('#chips [data-f=sday]'),
    open: g('#v3open'), x: g('#fhide'), tools: g('#v3tools'),
    walk: g('#chips [data-f=walk]'), vouch: g('#chips [data-f=vouch]'),
    sym: sr && {w: sr.width, h: sr.height},
    ck: cr && {t: cr.top, l: cr.left, r: cr.right, b: cr.bottom, w: cr.width, h: cr.height}};
}"""

KINDS = r"""() => [...document.querySelectorAll('#xlist > .card.xsh')].map(c => {
  const i = (SHELTERS.items || []).find(x => x.id === c.dataset.id) || {};
  return {sym: (c.querySelector('.xmkbox') || {}).dataset && c.querySelector('.xmkbox').dataset.sym, kind: i.kind || ''};
})"""

PINS = r"""() => { const pins = window.__shPins || []; const kinds = {};
  const sym = i => !i ? 'house' : (window.shDay && shDay(i) ? 'sun' : (window.shYouth && shYouth(i) ? 'youth' : 'house'));
  pins.filter(m => m._keep).forEach(m => { const i = m._si || {}; const k = sym(i) === 'sun' ? 'day' : sym(i) === 'youth' ? 'youth' : 'house'; kinds[k] = (kinds[k] || 0) + 1; });
  return kinds; }"""


def shown(box):
    return bool(box and box['show'])


class Source(unittest.TestCase):
    def test_markup_matches_the_draft(self):
        home = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
        css = open(os.path.join(ROOT, 'header.css'), encoding='utf-8').read()
        js = open(os.path.join(ROOT, 'layers.js'), encoding='utf-8').read()
        for s in ('data-f="shost"', 'data-f="youth"', 'data-f="sday"',
                  'Hostel or shelter', 'Young people', 'Day centre',
                  'Hostel neu loches', 'Pobl ifanc', 'Canolfan ddydd',
                  'M8 15.5l8-7.5 8 7.5V24H8z', 'M16 8v2.8', '>16<', '>25<'):
            self.assertIn(s, home)
        self.assertIn('grid-row:1', css)
        self.assertIn('[data-f=shost]', css)
        self.assertIn('shelterTypeOk(i)', js)
        self.assertIn("typeOn.shost=!typeOn.shost", js)
        # the old single chip label is no longer the filter
        self.assertNotIn('Young people (16–25)</span><span class="v-cy"', home)


@unittest.skipUnless(HAVE_CHROME, 'needs chrome + playwright')
class Chips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.srv, cls.base = serve()
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.chromium.launch(executable_path=CH)

    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop(); cls.srv.shutdown()

    def page(self, w):
        kw = dict(viewport={'width': w, 'height': 844}, service_workers='block')
        if w < 800:
            kw.update(is_mobile=True, has_touch=True)
        c = self.b.new_context(**kw)
        prepare(c, 'sh')
        self.addCleanup(c.close)
        return open_page(c, self.base, 'sh')

    def search(self, pg, q):
        pg.fill('#q', q)
        pg.press('#q', 'Enter')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length > 0"))

    def layout(self, pg, w):
        pg.evaluate('scrollTo(0,0)')
        box = pg.evaluate(LAYOUT)
        host, youth, day, open_, x, tools = box['host'], box['youth'], box['day'], box['open'], box['x'], box['tools']
        self.assertTrue(shown(host) and shown(youth) and shown(day), box)
        self.assertFalse(shown(box['walk']) or shown(box['vouch']), box)
        self.assertLess(abs(host['t'] - youth['t']), 4, box)
        self.assertLess(host['l'], youth['l'], box)
        self.assertLess(abs(day['t'] - open_['t']), 4, box)
        self.assertLess(abs(day['t'] - x['t']), 4, (w, 'reset shares the Day centre row', box))
        self.assertLess(day['l'], open_['l'], box)
        self.assertLess(open_['l'], x['l'], box)
        self.assertGreater(tools['t'], x['b'] - 2, box)
        self.assertLess(tools['t'] - x['b'], 24, (w, 'gap above List only', box))
        self.assertLessEqual(x['r'], box['vw'] + 1, box)
        self.assertLessEqual(box['sw'], box['vw'] + 1, box)
        ck = box.get('ck') or {}
        self.assertGreaterEqual(ck.get('l', -1), host['l'] - 0.6, box)
        self.assertLessEqual(ck.get('r', 10 ** 9), host['r'] + 0.6, box)
        self.assertGreaterEqual(ck.get('t', -1), host['t'] - 0.6, box)
        self.assertLessEqual(ck.get('b', 10 ** 9), host['b'] + 0.6, box)
        self.assertGreater(ck.get('w', 0), 16, box)
        self.assertAlmostEqual(box['sym']['w'], 20, delta=1)
        self.assertAlmostEqual(box['sym']['h'], 20, delta=1)
        # nothing else sits on the reset's row except Day centre and Open today
        mates = [n for n, b in (('host', host), ('youth', youth), ('day', day), ('open', open_), ('tools', tools)) if abs(b['t'] - x['t']) < 4]
        self.assertEqual(mates, ['day', 'open'], (w, mates))

    def test_rows_at_390_and_320(self):
        for w in (390, 320):
            with self.subTest(w=w):
                pg = self.page(w)
                self.layout(pg, w)
                self.assertEqual(pg.errs, [])

    def test_press_colours_and_welsh(self):
        pg = self.page(390)
        pg.click('#chips [data-f=youth]')
        pg.wait_for_timeout(200)
        paint = pg.evaluate("""() => { const e = document.querySelector('#chips [data-f=youth]');
          const s = getComputedStyle(e), k = getComputedStyle(e.querySelector('.ck'));
          return {bg: s.backgroundColor, pressed: e.getAttribute('aria-pressed'), tick: k.content || e.querySelector('.ck').textContent}; }""")
        self.assertEqual(paint['pressed'], 'true', paint)
        self.assertIn('245, 197, 24', paint['bg'], paint)
        pg.click('#xlang')
        self.assertTrue(until(pg, "() => document.documentElement.lang === 'cy'"))
        labels = pg.evaluate("""() => [...document.querySelectorAll('#chips [data-f=shost],#chips [data-f=youth],#chips [data-f=sday]')].map(e => e.innerText)""")
        self.assertTrue(any('Hostel neu loches' in t for t in labels), labels)
        self.assertTrue(any('Pobl ifanc' in t for t in labels), labels)
        self.assertTrue(any('Canolfan ddydd' in t for t in labels), labels)

    def test_each_type_filters_list_and_map(self):
        pg = self.page(390)
        self.search(pg, 'BN1 4NJ')
        mixed = pg.evaluate(KINDS)
        self.assertTrue({k['sym'] for k in mixed} >= {'house', 'sun', 'youth'}, mixed)
        pg.click('#chips [data-f=shost]')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length > 0"))
        kinds = pg.evaluate(KINDS)
        self.assertTrue(kinds and all(k['sym'] == 'house' for k in kinds), kinds)
        pins = pg.evaluate(PINS)
        self.assertEqual(set(pins), {'house'}, pins)
        pg.click('#chips [data-f=shost]')
        pg.click('#chips [data-f=youth]')
        self.assertTrue(until(pg, """() => { const cs=[...document.querySelectorAll('#xlist > .card.xsh')];
          const ok=i=>window.shYouth?shYouth(i):i.kind==='young_people';
          return cs.length >= 1 && cs.every(c => ok(SHELTERS.items.find(i => i.id === c.dataset.id) || {})); }"""))
        pg.click('#chips [data-f=youth]')
        self.search(pg, 'SW1A 1AA')
        pg.click('#chips [data-f=sday]')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length === 5"))
        self.assertTrue(all(k['sym'] == 'sun' for k in pg.evaluate(KINDS)))
        self.assertTrue(pg.evaluate("() => { const b=document.getElementById('xmore-sh'); return b && !b.hidden; }"))
        pg.click('#xmore-sh')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length > 5"))
        self.assertTrue(all(k['sym'] == 'sun' for k in pg.evaluate(KINDS)))
        pg.click('#v3open')
        pg.wait_for_timeout(600)
        left = pg.evaluate(KINDS)
        self.assertTrue(all(k['sym'] == 'sun' for k in left), left)
        pg.click('#fhide')
        pg.wait_for_timeout(400)
        pg.click('#ftab')
        self.assertTrue(until(pg, "() => !document.getElementById('v3filt').classList.contains('fclosed')"))
        pressed = pg.evaluate("""() => [...document.querySelectorAll('#chips [data-f=shost],#chips [data-f=youth],#chips [data-f=sday]')].map(e => e.getAttribute('aria-pressed'))""")
        self.assertEqual(pressed, ['false', 'false', 'false'], pressed)
        self.assertFalse(pg.evaluate("() => document.getElementById('openToday').checked"))
        self.assertEqual(pg.errs, [])

    def test_food_bank_chips_return(self):
        pg = self.page(390)
        self.assertFalse(shown(pg.evaluate(LAYOUT)['walk']))
        pg.click('.v3b[data-l=fb]')
        self.assertTrue(until(pg, "() => document.documentElement.dataset.v3k === 'fb'"))
        pg.wait_for_timeout(300)
        box = pg.evaluate(LAYOUT)
        self.assertTrue(shown(box['walk']) and shown(box['vouch']), box)
        self.assertFalse(shown(box['host']) or shown(box['youth']) or shown(box['day']), box)
        pg.click('.v3b[data-l=sh]')
        self.assertTrue(until(pg, "() => document.documentElement.dataset.v3k === 'sh'"))
        pg.wait_for_timeout(300)
        box = pg.evaluate(LAYOUT)
        self.assertTrue(shown(box['host']) and not shown(box['walk']), box)
