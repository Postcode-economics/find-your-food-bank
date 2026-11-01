"""Show more for the shelters and warm spaces lists (#xlist, layers.js nearX).

Same rules as the food bank list (showmore.js, window.SHOW_LIMITS = {first: 5, more: 10}):
the 5 nearest first, each press appends the next 10 nearest, the button hides when none are left,
and a new search, Verified only or Open today starts again at 5. One button per list (#xmore-sh,
#xmore-ws), English/Welsh label, a real <button> (Enter/Space), no page jump, no map move per press,
cards appended in place (the v3.js #xlist observer sees additions only), and a click handler on the
document so the button restored from the saved search (offline) still works. Ended places are
labelled and listed after the others; Open today leaves them out.

Static checks run in the plain pytest job. Chrome click-through runs in browser-tests; the iPhone
class needs Playwright WebKit (iphone-webkit job). Tiles are stubbed and postcodes.io is refused, so
searches use the bundled outcodes.json and nothing leaves the machine.
"""
import functools, hashlib, http.server, os, re, sys, threading, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, 'scripts'))
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()
CH = '/usr/bin/google-chrome'
SHOTS = os.environ.get('HELPMAP_SHOTS')
try:
    import playwright  # noqa: F401
    HAVE_PW = True
except Exception:
    HAVE_PW = False
HAVE_CHROME = HAVE_PW and os.path.exists(CH)
ENDED = 'This season’s scheme has ended'

# The expected order, worked out here from the data (not from layers.js): Verified only keeps verified places and
# ones with times checked, Open today drops ended and closed-today places, ended places go last, then nearest first.
# A Referral hostel has no pin, so it is on the council-area list only and is not in this nearest list.
EXPECT = """([k, vo, ot]) => {const D = k === 'sh' ? window.SHELTERS : window.WARMSPACES; if (!D || !lastNear) return null;
  const [a, b] = lastNear, r = x => x * Math.PI / 180;
  const hv = (la, ln) => 12742 * Math.asin(Math.sqrt(Math.sin(r(la - a) / 2) ** 2 + Math.cos(r(a)) * Math.cos(r(la)) * Math.sin(r(ln - b) / 2) ** 2));
  return D.items.filter(i => i.card_type !== 'referral_hostel' && typeof i.lat === 'number' && typeof i.lng === 'number' && (!vo || i.tier !== 'unverified' || timesChecked(i)) && !(ot && (i.ended || V3.shutToday(k, i))) && (k !== 'sh' || shelterTypeOk(i)))
    .map(i => ({id: i.id, e: !!i.ended, d: hv(i.lat, i.lng)})).sort((x, y) => (x.e - y.e) || x.d - y.d).map(x => x.id)}"""
IDS = "k => [...document.querySelectorAll('#xlist > .card.x' + k)].map(c => c.dataset.id)"
BTN = """k => {const b = document.getElementById('xmore-' + k); if (!b) return null; const s = getComputedStyle(b);
  return {tag: b.tagName, type: b.type, shown: !b.hidden && s.display !== 'none' && b.getClientRects().length > 0,
    exp: b.getAttribute('aria-expanded'), ctl: b.getAttribute('aria-controls'), text: b.innerText.trim(), h: b.getBoundingClientRect().height,
    focused: document.activeElement === b, last: b.previousElementSibling && b.previousElementSibling.classList.contains('x' + k)}}"""
VIEW = "() => ({x: scrollX, y: scrollY, z: map.getZoom(), c: map.getCenter().toString()})"
FILTER_STATE = """k => {const vo = document.querySelector('#xlist .v3vo[data-k=' + k + ']'); return {
  vo: vo && vo.getAttribute('aria-pressed') === 'true',
  ot: !!(document.getElementById('openToday') || {}).checked}; }"""


def want_ids(pg, k):
    f = pg.evaluate(FILTER_STATE, k)
    return pg.evaluate(EXPECT, [k, f['vo'], f['ot']])


def card_count(pg, k):
    return pg.evaluate("k => document.querySelectorAll('#xlist > .card.x' + k).length", k)


class Static(unittest.TestCase):
    def test_layers_js_contract(self):
        js = rd('layers.js')
        for s in ("window.showMoreX=", "id=\"xmore-${k}\"", 'aria-controls="xlist"', '<span class="v-en">Show more</span>',
                  '<span class="v-cy" lang="cy">Dangos mwy</span>', "document.addEventListener('click',e=>{const b=e.target.closest('#xlist .xmore')",
                  'btn.before(tpl.content)', 'focus({preventScroll:true})', 'window.SHOW_LIMITS', 'overflow-anchor:none'):
            self.assertIn(s, js)
        i = js.index('window.showMoreX=')
        body = js[i:js.index('document.addEventListener', i)]
        for bad in ('innerHTML=', 'fitBounds', 'setView', 'nearX(', 'nearest('):
            self.assertNotIn(bad, body.replace('tpl.innerHTML=', ''), 'Show more must append in place and never move the map')
        self.assertIn('M8 15.5l8-7.5 8 7.5V24H8z', js)  # house symbol, same box as the sun and 16/25
        self.assertIn('M3 3h26v26H21l-5 9-5-9H3z', js)  # existing square pin outline kept
        self.assertIn("st.id='xsym'", js)
        self.assertIn('shelterTypeOk(i)', js)
        self.assertIn('mountShelterStrip', rd('v3.js'))
        home = rd('index.html')
        self.assertIn('data-f="youth"', home)
        self.assertIn('data-f="shost"', home)
        self.assertIn('data-f="sday"', home)
        self.assertIn('Hostel or shelter', home)
        self.assertIn('Young people', home)
        self.assertIn('Day centre', home)
        self.assertIn('Pobl ifanc', home)

    def test_cache_tag_is_the_new_layers_js(self):
        lh = 'h' + hashlib.sha256(open(os.path.join(R, 'layers.js'), 'rb').read()).hexdigest()[:12]
        for f in ('index.html', 'sw.js'):
            self.assertEqual(re.findall(r'layers\.js\?v=(h[0-9a-f]+)', rd(f)), [lh], f)


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, 'http://127.0.0.1:%d' % s.server_address[1]


HM = 'https://helpmap.uk'


def serve_as_helpmap(c):
    """WebKit: the checkout answered as https://helpmap.uk (as test_iphone_map_fix), no server and no real network."""
    import mimetypes

    def local(route):
        path = route.request.url.split(HM, 1)[1].split('?')[0].split('#')[0] or '/'
        f = os.path.join(R, path.lstrip('/'))
        f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
        if not os.path.isfile(f):
            return route.fulfill(status=404, body='')
        route.fulfill(status=200, body=open(f, 'rb').read(), headers={
            'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})
    c.route(HM + '/**', local)
    c.route(HM + '/', local)


def until(pg, js, arg=None, secs=25):
    for _ in range(secs * 4):
        try:
            if pg.evaluate(js, arg):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


def prepare(c, k):
    from check_browser import stub_map_tiles
    c.add_init_script("try{localStorage.setItem('v3layer','%s')}catch(e){}" % k)
    stub_map_tiles(c)
    c.route(re.compile(r'https?://api\.postcodes\.io/.*'), lambda r: r.abort())


def open_page(c, base, k, q='?nocount'):
    from site_ready import wait_ready
    pg = c.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(base + '/' + q, wait_until='domcontentloaded')
    wait_ready(pg)
    assert until(pg, "k => window[k === 'sh' ? 'SHELTERS' : 'WARMSPACES'] && document.querySelector('.v3b[data-l=' + k + '][aria-checked=true]')", k), 'layer not ready'
    pg.errs = errs
    return pg


def bring_into_view(pg, sel):
    """Put the element mid-screen and wait for the page to stop scrolling (a search scrolls smoothly to the list),
    so the press itself needs no scroll and any later movement is the button's doing."""
    last = None
    for _ in range(40):
        pg.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center', behavior: 'instant'})", sel)
        pg.wait_for_timeout(250)
        last = pg.evaluate("""s => {const y = scrollY, r = document.querySelector(s).getBoundingClientRect();
            return new Promise(ok => setTimeout(() => ok({still: scrollY === y, y, y2: scrollY, top: r.top, bottom: r.bottom, vh: innerHeight}), 250))}""", sel)
        if last['still'] and last['top'] >= 0 and last['bottom'] <= last['vh'] + 48:
            return
    raise AssertionError('could not bring %s into view: %r' % (sel, last))


def search(pg, k, q):
    pg.fill('#q', q)
    pg.press('#q', 'Enter')
    assert until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length > 0 && lastNear", k), 'no %s cards for %s' % (k, q)
    pg.wait_for_timeout(700)  # the delayed map re-fit (250 ms) and the first-search scroll settle


class Journey:
    """Shared click-through checks; subclasses supply the browser and the press (click or tap)."""

    def press(self, pg, k):
        raise NotImplementedError

    def check_first_page(self, pg, k, vo=False, ot=False):
        want = pg.evaluate(EXPECT, [k, vo, ot])
        self.assertTrue(want and len(want) > 15, (k, want and len(want)))
        self.assertEqual(pg.evaluate(IDS, k), want[:5], (k, 'the 5 nearest first'))
        b = pg.evaluate(BTN, k)
        self.assertTrue(b and b['shown'], (k, b))
        self.assertEqual((b['tag'], b['type'], b['ctl'], b['exp']), ('BUTTON', 'button', 'xlist', 'false'), b)
        self.assertTrue(b['last'], 'button sits after the last card of its list')
        self.assertGreaterEqual(b['h'], 44)
        return want

    def press_once(self, pg, k, n_before, want):
        pg.evaluate("""() => {window.__rm = 0; window.__keep = document.querySelector('#xlist > .card'); window.__lh = document.querySelector('#xlist > .lh');
          if (window.__mo) window.__mo.disconnect(); window.__mo = new MutationObserver(ms => ms.forEach(m => window.__rm += m.removedNodes.length));
          window.__mo.observe(document.getElementById('xlist'), {childList: true})}""")
        bring_into_view(pg, '#xmore-' + k)
        v0 = pg.evaluate(VIEW)
        self.press(pg, k)
        n = min(n_before + 10, len(want))
        self.assertTrue(until(pg, "([k, n]) => document.querySelectorAll('#xlist > .card.x' + k).length === n", [k, n], 10),
                        (k, n, len(pg.evaluate(IDS, k))))
        pg.wait_for_timeout(400)
        self.assertEqual(pg.evaluate(IDS, k), want[:n], (k, 'nearest first after a press'))
        v1 = pg.evaluate(VIEW)
        self.assertLessEqual(abs(v1['y'] - v0['y']), 1, ('page jumped', v0, v1))
        self.assertEqual((v1['z'], v1['c']), (v0['z'], v0['c']), ('map moved', v0, v1))
        kept = pg.evaluate("() => window.__rm === 0 && document.contains(window.__keep) && document.contains(window.__lh)")
        self.assertTrue(kept, '#xlist was rebuilt instead of appended to')
        return n

    def run_journey(self, pg, k, shots=None):
        want = self.check_first_page(pg, k)
        if shots:
            bring_into_view(pg, '#xmore-' + k)
            pg.screenshot(path=shots + '-1-first-5.png')
        n = self.press_once(pg, k, 5, want)
        self.assertEqual(n, 15)
        b = pg.evaluate(BTN, k)
        self.assertTrue(b['shown'] and b['exp'] == 'true', b)
        if shots:
            pg.screenshot(path=shots + '-2-after-press.png')
        n = self.press_once(pg, k, n, want)
        self.assertEqual(n, 25)
        # a new search starts again at 5
        search(pg, k, 'M1 1AE')
        want = self.check_first_page(pg, k)
        self.press_once(pg, k, 5, want)
        return want

    def check_filters_reset(self, pg, k):
        want = self.check_first_page(pg, k)
        self.press_once(pg, k, 5, want)
        pg.click('#xlist .v3vo[data-k=%s]' % k)  # Verified only
        self.assertTrue(until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length <= 5", k, 10))
        self.check_first_page(pg, k, vo=True)
        pg.click('#xlist .v3vo[data-k=%s]' % k)
        self.assertTrue(until(pg, "k => document.querySelector('#xlist .v3vo[data-k=' + k + ']').getAttribute('aria-pressed') === 'false'", k, 10))
        want = self.check_first_page(pg, k)
        self.press_once(pg, k, 5, want)
        pg.click('#v3open')  # Open today
        self.assertTrue(until(pg, "() => document.getElementById('openToday').checked"))
        self.assertTrue(until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length === 5", k, 10))
        want = self.check_first_page(pg, k, ot=True)
        self.press_once(pg, k, 5, want)
        pg.click('#v3open')
        self.assertTrue(until(pg, "() => !document.getElementById('openToday').checked"))
        self.assertTrue(until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length === 5", k, 10))

    def assert_show_more_one_press(self, pg, k):
        """Show more adds the next filtered batch, or the button is hidden when nothing remains."""
        want = want_ids(pg, k)
        n = card_count(pg, k)
        btn = pg.evaluate(BTN, k)
        self.assertEqual(pg.evaluate(IDS, k), want[:n], (k, 'listed ids match filtered rank'))
        if len(want) <= n:
            self.assertTrue(btn is None or not btn['shown'], (k, len(want), n))
            return
        self.assertTrue(btn and btn['shown'], (k, n, len(want)))
        self.press_once(pg, k, n, want)

    def check_to_the_end_and_keyboard(self, pg, k):
        want = self.check_first_page(pg, k)
        pg.focus('#xmore-' + k)
        pg.keyboard.press('Enter')
        self.assertTrue(until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length === 15", k, 10))
        self.assertTrue(pg.evaluate(BTN, k)['focused'], 'focus stays on Show more while more are left')
        pg.keyboard.press('Space')
        self.assertTrue(until(pg, "k => document.querySelectorAll('#xlist > .card.x' + k).length === 25", k, 10))
        self.assertTrue(pg.evaluate(BTN, k)['focused'])
        for _ in range(200):
            if not pg.evaluate(BTN, k)['shown']:
                break
            pg.keyboard.press('Enter')
            pg.wait_for_timeout(30)
        self.assertEqual(pg.evaluate(IDS, k), want, 'every place, nearest first, once each')
        b = pg.evaluate(BTN, k)
        self.assertFalse(b['shown'], 'button hides when none are left')
        self.assertEqual(b['exp'], 'true')
        last_first = want[(len(want) - 6) // 10 * 10 + 5]
        f = pg.evaluate("() => {const a = document.activeElement; const c = a && a.closest('.card'); return c ? [a.tagName, c.dataset.id] : null}")
        self.assertEqual(f, ['H3', last_first], 'focus moves to the first card of the last batch')


@unittest.skipUnless(HAVE_CHROME, 'needs chrome + playwright')
class Chrome(Journey, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.srv, cls.base = serve()
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.chromium.launch(executable_path=CH)

    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop(); cls.srv.shutdown()

    def ctx(self, k, w=390):
        kw = dict(viewport={'width': w, 'height': 844}, service_workers='block')
        if w < 800:
            kw.update(is_mobile=True, has_touch=True)
        c = self.b.new_context(**kw)
        prepare(c, k)
        self.addCleanup(c.close)
        return c

    def press(self, pg, k):
        pg.click('#xmore-' + k)

    def test_show_more_under_each_filter_state(self):
        """Show more loads the next filtered batch (or hides) for every chip and Open today combination."""
        pg = open_page(self.ctx('sh'), self.base, 'sh')
        search(pg, 'sh', 'BN17 5LF')

        def apply_shelter_filters(host=False, youth=False, day=False, open_today=False):
            for sel, on in (('[data-f=shost]', host), ('[data-f=youth]', youth), ('[data-f=sday]', day)):
                cur = pg.evaluate("s => document.querySelector('#chips '+s).getAttribute('aria-pressed')==='true'", sel)
                if cur != on:
                    pg.click('#chips ' + sel)
                    pg.wait_for_timeout(200)
            ot = pg.evaluate("() => !!document.getElementById('openToday').checked")
            if ot != open_today:
                pg.click('#v3open')
            self.assertTrue(until(pg, "([host, youth, day]) => {"
              "const h=document.querySelector('#chips [data-f=shost]').getAttribute('aria-pressed')==='true';"
              "const y=document.querySelector('#chips [data-f=youth]').getAttribute('aria-pressed')==='true';"
              "const d=document.querySelector('#chips [data-f=sday]').getAttribute('aria-pressed')==='true';"
              "return h===host&&y===youth&&d===day;}", [host, youth, day], 10))
            self.assertTrue(until(pg, "ot => !!document.getElementById('openToday').checked === ot", open_today, 10))
            self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length > 0", None, 10))

        scenarios = [
            dict(host=False, youth=False, day=False, open_today=False),
            dict(host=True, youth=False, day=False, open_today=False),
            dict(host=False, youth=False, day=True, open_today=False),
            dict(host=False, youth=True, day=False, open_today=False),
            dict(host=True, youth=True, day=False, open_today=False),
            dict(host=False, youth=False, day=True, open_today=True),
            dict(host=True, youth=False, day=False, open_today=True),
        ]
        for sc in scenarios:
            with self.subTest(**sc):
                apply_shelter_filters(**sc)
                pg.wait_for_timeout(400)
                n0 = card_count(pg, 'sh')
                if n0 == 0:
                    continue
                self.assert_show_more_one_press(pg, 'sh')

        pg = open_page(self.ctx('ws'), self.base, 'ws')
        search(pg, 'ws', 'BN17 5LF')
        for vo, ot in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(layer='ws', vo=vo, ot=ot):
                cur_vo = pg.evaluate("() => document.querySelector('#xlist .v3vo[data-k=ws]').getAttribute('aria-pressed')==='true'")
                if cur_vo != vo:
                    pg.click('#xlist .v3vo[data-k=ws]')
                cur_ot = pg.evaluate("() => !!document.getElementById('openToday').checked")
                if cur_ot != ot:
                    pg.click('#v3open')
                want_n = len(want_ids(pg, 'ws'))
                self.assertTrue(until(pg, "n => document.querySelectorAll('#xlist > .card.xws').length === Math.min(5, n)", want_n, 10))
                self.assert_show_more_one_press(pg, 'ws')

        pg = open_page(self.ctx('sh'), self.base, 'sh')
        pg.click('.v3b[data-l=fb]')
        self.assertTrue(until(pg, "() => document.documentElement.dataset.v3k === 'fb'"))
        pg.wait_for_timeout(300)
        pg.fill('#q', 'BN17 5LF')
        pg.press('#q', 'Enter')
        self.assertTrue(until(pg, "() => document.querySelectorAll('#list > .card').length === 5"))
        for walk, vouch in ((False, False), (True, False), (False, True)):
            with self.subTest(layer='fb', walk=walk, vouch=vouch):
                for sel, on in (('[data-f=walk]', walk), ('[data-f=vouch]', vouch)):
                    cur = pg.evaluate("s => document.querySelector('#chips '+s).getAttribute('aria-pressed')==='true'", sel)
                    if cur != on:
                        pg.click('#chips ' + sel)
                pg.wait_for_timeout(500)
                n = pg.evaluate("() => document.querySelectorAll('#list > .card').length")
                btn = pg.evaluate("""() => {const b=document.getElementById('showmore'); if(!b)return null;
                  const s=getComputedStyle(b); return {shown:!b.hidden&&s.display!=='none'&&b.getClientRects().length>0};}""")
                total = pg.evaluate("""() => {
                  if (typeof items === 'undefined' || typeof vis !== 'function') return 0;
                  var c = 0;
                  for (var k = 0; k < items.length; k++) {
                    if (!vis(k)) continue;
                    if (typeof nc === 'function' && nc(items[k])) continue;
                    c++;
                  }
                  return c;}""")
                if total <= n:
                    self.assertFalse(btn and btn['shown'])
                else:
                    self.assertTrue(btn and btn['shown'])
                    before = n
                    pg.click('#showmore')
                    self.assertTrue(until(pg, "b => document.querySelectorAll('#list > .card').length > b", before, 10))
        self.assertEqual(pg.errs, [])

    def test_shelter_filters_keep_show_more(self):
        """Day centres and Young people (16–25) filter the shelters list. Show more still pages what remains."""
        for w in (390, 1366):
            with self.subTest(w=w):
                pg = open_page(self.ctx('sh', w), self.base, 'sh')
                search(pg, 'sh', 'SW1A 1AA')
                self.assertTrue(pg.evaluate("() => {const e=document.getElementById('xsym');const s=getComputedStyle(e);return e.getClientRects().length>0&&s.display!=='none'}"))
                pg.click('#xlist .v3dc')
                self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length === 5"))
                ids = pg.evaluate(IDS, 'sh')
                kinds = pg.evaluate("ids => ids.map(id => { const i = SHELTERS.items.find(x => x.id === id) || {}; return window.shDay && shDay(i) ? 'day' : i.kind; })", ids)
                self.assertTrue(kinds and all(k == 'day' for k in kinds), kinds)
                self.assertTrue(pg.evaluate(BTN, 'sh')['shown'])
                self.press(pg, 'sh')
                self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length > 5"))
                self.assertTrue(all(k == 'day' for k in pg.evaluate(
                    "ids => ids.map(id => { const i = SHELTERS.items.find(x => x.id === id) || {}; return window.shDay && shDay(i) ? 'day' : i.kind; })", pg.evaluate(IDS, 'sh'))))
                pg.click('#xlist .v3dc')
                self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length === 5"))
                pg.click('#chips [data-f=youth]')
                self.assertTrue(until(pg, """() => {const cs=[...document.querySelectorAll('#xlist > .card.xsh')];
                  const ok=i=>window.shYouth?shYouth(i):i.kind==='young_people';
                  return cs.length>=1 && cs.every(c => ok(SHELTERS.items.find(i => i.id === c.dataset.id) || {}));}"""))
                btn = pg.evaluate(BTN, 'sh')
                self.assertTrue(btn is None or not btn['shown'])
                pg.click('#chips [data-f=youth]')
                self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xsh').length === 5 && !!document.getElementById('xmore-sh')"))
                self.assertTrue(pg.evaluate(BTN, 'sh')['shown'])
                self.assertEqual(pg.errs, [])

    def test_click_through_both_lists_phone_and_desktop(self):
        for w in (390, 1366):
            for k in ('sh', 'ws'):
                with self.subTest(w=w, k=k):
                    pg = open_page(self.ctx(k, w), self.base, k)
                    search(pg, k, 'BN17 5LF')
                    self.run_journey(pg, k)
                    self.assertEqual(pg.errs, [])

    def test_verified_only_and_open_today_reset_to_five(self):
        for k in ('sh', 'ws'):
            with self.subTest(k=k):
                pg = open_page(self.ctx(k), self.base, k)
                search(pg, k, 'SW1A 1AA')
                self.check_filters_reset(pg, k)

    def test_keyboard_to_the_end(self):
        for k in ('sh', 'ws'):
            with self.subTest(k=k):
                pg = open_page(self.ctx(k, 1366), self.base, k)
                search(pg, k, 'BN17 5LF')
                self.check_to_the_end_and_keyboard(pg, k)

    def test_welsh_label_and_language_switch_keeps_the_list(self):
        pg = open_page(self.ctx('ws'), self.base, 'ws')
        search(pg, 'ws', 'BN17 5LF')
        want = self.check_first_page(pg, 'ws')
        self.assertEqual(pg.evaluate(BTN, 'ws')['text'], 'Show more')
        self.press_once(pg, 'ws', 5, want)
        pg.click('#xlang')
        self.assertTrue(until(pg, "() => document.documentElement.lang === 'cy'"))
        self.assertTrue(until(pg, "() => (document.getElementById('xmore-ws') || {}).innerText === 'Dangos mwy'", None, 10))
        self.assertEqual(pg.evaluate(IDS, 'ws'), want[:15], 'switching language keeps the places already shown')
        self.press_once(pg, 'ws', 15, want)
        pg.click('#xlang')
        self.assertTrue(until(pg, "() => (document.getElementById('xmore-ws') || {}).innerText === 'Show more'", None, 10))

    def test_separate_buttons_per_list(self):
        pg = open_page(self.ctx('sh'), self.base, 'sh')
        search(pg, 'sh', 'BN17 5LF')
        pg.evaluate("() => document.querySelector('.xt[data-l=ws]').click()")  # both layers on (the old toggle row)
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xws').length === 5 && document.querySelectorAll('#xlist > .card.xsh').length === 5"))
        ids = pg.evaluate("() => [...document.querySelectorAll('#xlist .xmore')].map(b => b.id)")
        self.assertEqual(sorted(ids), ['xmore-sh', 'xmore-ws'])
        self.assertEqual(pg.evaluate("() => document.querySelectorAll('[id^=xmore-]').length"), 2)
        pg.evaluate("() => document.getElementById('xmore-ws').click()")
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xws').length === 15"))
        self.assertEqual(len(pg.evaluate(IDS, 'sh')), 5, 'the shelters list is untouched')
        order = pg.evaluate("() => [...document.querySelectorAll('#xlist > *')].map(e => e.id || e.className.split(' ').find(c => /^x(sh|ws)$/.test(c)) || e.className)")
        sh_btn, ws_btn = order.index('xmore-sh'), order.index('xmore-ws')
        self.assertTrue(all(x == 'xsh' for x in order[sh_btn - 5:sh_btn]), order)
        self.assertTrue(all(x == 'xws' for x in order[ws_btn - 15:ws_btn]), order)

    def test_ended_places_labelled_last_or_left_out(self):
        pg = open_page(self.ctx('ws'), self.base, 'ws')
        search(pg, 'ws', 'BN17 5LF')
        want = pg.evaluate(EXPECT, ['ws', False, False])
        ended = want[:3]
        pg.evaluate("ids => {WARMSPACES.items.forEach(i => {if (ids.includes(i.id)) i.ended = true}); nearest(...lastNear)}", ended)
        self.assertTrue(until(pg, "id => !document.querySelector('#xlist > .card.xws[data-id=\"' + id + '\"]')", ended[0], 10))
        want = self.check_first_page(pg, 'ws')
        self.assertEqual(want[-3:], sorted(ended, key=want.index))
        for _ in range(100):
            if not pg.evaluate(BTN, 'ws')['shown']:
                break
            pg.click('#xmore-ws')
            pg.wait_for_timeout(30)
        self.assertEqual(pg.evaluate(IDS, 'ws'), want)
        labels = pg.evaluate("ids => ids.map(id => (document.querySelector('#xlist > .card.xws[data-id=\"' + id + '\"] .xw') || {}).textContent || '')", ended)
        self.assertTrue(all(ENDED in s for s in labels), labels)
        pg.click('#v3open')
        self.assertTrue(until(pg, "() => document.getElementById('openToday').checked"))
        self.assertTrue(until(pg, "() => document.querySelectorAll('#xlist > .card.xws').length === 5", None, 10))
        want = self.check_first_page(pg, 'ws', ot=True)
        self.assertFalse(set(ended) & set(want))
        for _ in range(100):
            if not pg.evaluate(BTN, 'ws')['shown']:
                break
            pg.click('#xmore-ws')
            pg.wait_for_timeout(30)
        self.assertEqual(pg.evaluate(IDS, 'ws'), want)
        self.assertEqual(pg.evaluate("() => document.querySelectorAll('#xlist .card.xws .xw').length"),
                         pg.evaluate("() => document.querySelectorAll('#xlist .card.xws[data-id] p.xw').length"))
        self.assertFalse(any(ENDED in s for s in pg.evaluate("() => [...document.querySelectorAll('#xlist .card.xws .xw')].map(e => e.textContent)")))

    def test_works_after_offline_restore(self):
        for k in ('sh', 'ws'):
            with self.subTest(k=k):
                c = self.ctx(k)
                pg = open_page(c, self.base, k)
                search(pg, k, 'BN17 5LF')
                want = pg.evaluate(EXPECT, [k, False, False])
                pg.close()
                # next visit with no connection: nothing re-runs the search (fresh=1), the saved list is put back
                pg = open_page(c, self.base, k, '?nocount&fresh=1')
                self.assertEqual(pg.evaluate("() => document.querySelectorAll('#xlist .card').length"), 0)
                c.set_offline(True)
                pg.evaluate("() => window.__hmGoOffline()")
                self.assertTrue(until(pg, "() => !document.getElementById('xoff').hidden"))
                self.assertEqual(pg.evaluate(IDS, k), want[:5], 'restored first page')
                self.assertTrue(pg.evaluate(BTN, k)['shown'])
                n = self.press_once(pg, k, 5, want)
                self.assertEqual(n, 15)
                self.press_once(pg, k, 15, want)
                c.set_offline(False)


def have_webkit():
    if not HAVE_PW:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE_WEBKIT = have_webkit()


@unittest.skipUnless(HAVE_WEBKIT, 'needs playwright webkit')
class IPhone(Journey, unittest.TestCase):
    """Real WebKit, iPhone 13 and iPhone SE profiles, real taps. HELPMAP_SHOTS=dir saves phone screenshots."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.pw = sync_playwright().start()
        cls.b = cls.pw.webkit.launch()

    @classmethod
    def tearDownClass(cls):
        cls.b.close(); cls.pw.stop()

    def phone(self, dev, k, init=''):
        d = dict(self.pw.devices[dev])
        d.pop('default_browser_type', None)
        c = self.b.new_context(**d, service_workers='block')
        self.addCleanup(c.close)
        serve_as_helpmap(c)
        if init:
            c.add_init_script(init)
        prepare(c, k)
        return open_page(c, HM, k)

    def press(self, pg, k):
        pg.tap('#xmore-' + k)

    def shots(self, name):
        if not SHOTS:
            return None
        os.makedirs(SHOTS, exist_ok=True)
        return os.path.join(SHOTS, name)

    def test_tap_through_on_iphone(self):
        for dev in ('iPhone 13', 'iPhone SE'):
            for k in ('ws', 'sh'):
                for theme in ('dark', 'light'):
                    with self.subTest(dev=dev, k=k, theme=theme):
                        pg = self.phone(dev, k, "try{localStorage.setItem('light','1')}catch(e){}" if theme == 'light' else '')
                        search(pg, k, 'BN17 5LF')
                        self.run_journey(pg, k, self.shots('%s-%s-%s' % (dev.replace(' ', ''), k, theme)))
                        self.assertEqual(pg.errs, [])

    def test_welsh_on_iphone(self):
        pg = self.phone('iPhone 13', 'ws', "try{localStorage.setItem('lang','cy')}catch(e){}")
        search(pg, 'ws', 'BN17 5LF')
        self.assertEqual(pg.evaluate(BTN, 'ws')['text'], 'Dangos mwy')
        s = self.shots('iPhone13-ws-welsh.png')
        if s:
            bring_into_view(pg, '#xmore-ws')
            pg.screenshot(path=s)
        want = pg.evaluate(EXPECT, ['ws', False, False])
        self.press_once(pg, 'ws', 5, want)


if __name__ == '__main__':
    unittest.main()
