"""Stale sw.js under a reused tag (27 Oct 2026 outage, after PR 193).

Cloudflare stored the old fyfb-v90 worker under sw.js?v=57 because that URL was fetched on live before the deploy, so
Safari kept the old worker and the grey map. The tag is now a hash of sw.js (its ?v= precache entries left out, so the
refresh workflows' SHELL sync can't make it drift), and index.html clears fyfb-v90 / fyfb-tiles leftovers once.
"""
import hashlib, os, re, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
rd = lambda f: open(os.path.join(R, f), encoding='utf-8').read()
USED_TAGS = {'57'} | {str(n) for n in range(1, 57)}  # every numeric tag ever used, including the poisoned v=57


def sw_tag():
    return 'h' + hashlib.sha256(re.sub(r"\?v=[\w.-]+", '', rd('sw.js')).encode()).hexdigest()[:12]


class Tag(unittest.TestCase):
    def test_registration_uses_the_content_hash(self):
        m = re.search(r"register\('sw\.js\?v=([\w.-]+)'", rd('layers.js'))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), sw_tag(), 'sw.js changed: set layers.js register tag to sha256 of sw.js (no ?v= parts)')
        self.assertNotIn(m.group(1), USED_TAGS)
        self.assertIn("updateViaCache:'none'", rd('layers.js'))

    def test_layers_js_tag_matches_its_content(self):
        lh = 'h' + hashlib.sha256(open(os.path.join(R, 'layers.js'), 'rb').read()).hexdigest()[:12]
        self.assertIn('layers.js?v=' + lh, rd('index.html'))
        self.assertIn('layers.js?v=' + lh, rd('sw.js'))

    def test_old_cache_self_heal_is_in_the_head(self):
        h = rd('index.html'); i = h.index("k='hmHealOld'")
        self.assertLess(i, h.index('</head>'))
        for s in ("'fyfb-v90'", "'fyfb-tiles'", 'caches.delete', 'unregister()', 'location.reload()', 'sessionStorage.setItem(k'):
            self.assertIn(s, h[i:i + 900])


from test_iphone_map_fix import HAVE, IPhone, BASE, png, old_sw, until, PAINTED, STATE, OFM
SHOTS = os.environ.get('HELPMAP_SHOTS', '/tmp/helpmap_sw_shots')


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class StaleWorker(unittest.TestCase):
    _ctx = IPhone._ctx
    def test_poisoned_old_worker_heals_once_and_map_paints(self):
        """The old v90 worker is still served (as Cloudflare did); the page clears its caches and reloads exactly once."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, c, holder = self._ctx(p, sw_body=old_sw('e3982436c'))
            c.route('**://tile.openstreetmap.org/**', png)
            loads = []
            pg = c.new_page(); pg.on('load', lambda *_: loads.append(1))
            pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, "async () => (await caches.keys()).includes('fyfb-v90')", 30), 'old worker made no fyfb-v90 cache')
            holder['sw'] = None  # the deploy: this checkout's sw.js under its new hash tag
            n = len(loads)
            pg.reload(wait_until='load')
            self.assertTrue(until(pg, "() => sessionStorage.getItem('hmHealOld')==='1'", 20), 'self-heal did not run')
            self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return !k.includes('fyfb-v90') && !k.includes('fyfb-tiles') }", 30),
                            pg.evaluate('async () => await caches.keys()'))
            self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
            pg.wait_for_timeout(2000)
            self.assertLessEqual(len(loads) - n, 3, 'reload loop')
            self.assertEqual(pg.evaluate(STATE)['active'], 'osm')
            b.close()

    def _healed(self, p):
        """(1) Old v90 worker + fyfb-v90/fyfb-tiles caches installed, then the new build: heals exactly once, ends on the
        new caches, OSM draws. Returns the live page for the offline / backup follow-ups."""
        b, c, holder = self._ctx(p, sw_body=old_sw('e3982436c'))
        net = {'off': False, 'osm': 0}
        def osm(route):
            if net['off']:
                return route.abort('internetdisconnected')
            net['osm'] += 1; png(route)
        c.route('**://tile.openstreetmap.org/**', osm)
        pg = c.new_page(); navs = []
        pg.on('framenavigated', lambda f: f == pg.main_frame and navs.append(f.url))
        pg.goto(BASE + '/?nocount', wait_until='load')
        self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return k.includes('fyfb-v90') && k.includes('fyfb-tiles') }", 30),
                        pg.evaluate('async () => await caches.keys()'))
        holder['sw'] = None
        before = len(navs)
        pg.goto(BASE + '/?nocount', wait_until='load')
        self.assertTrue(until(pg, "async () => { const k = await caches.keys(); return k.includes('fyfb-v92') && k.includes('fyfb-tiles2') && !k.includes('fyfb-v90') && !k.includes('fyfb-tiles') }", 40),
                        pg.evaluate('async () => await caches.keys()'))
        self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
        pg.wait_for_timeout(3000)
        self.assertEqual(len(navs) - before, 2, ('expected the visit plus exactly one heal reload', navs[before:]))
        self.assertEqual(pg.evaluate("() => sessionStorage.getItem('hmHealOld')"), '1')
        self.assertTrue(pg.evaluate("() => !!navigator.serviceWorker.controller && /sw\\.js\\?v=h[0-9a-f]{12}$/.test(navigator.serviceWorker.controller.scriptURL)"),
                        pg.evaluate("() => navigator.serviceWorker.controller && navigator.serviceWorker.controller.scriptURL"))
        return b, c, pg, net, navs

    def test_heal_once_then_offline_still_works(self):
        """(1) + (2): self-heal and the offline cache together."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, c, pg, net, navs = self._healed(p)
            pg.reload(wait_until='load')  # a second online visit fills the new caches under the new worker
            self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
            pg.wait_for_timeout(1500)
            net['off'] = True
            c.unroute_all(behavior='ignoreErrors')  # no test server any more: only the worker's caches can answer
            c.set_offline(True); n = len(navs)
            pg.reload(wait_until='load')
            self.assertTrue(until(pg, "() => !!document.querySelector('#map .leaflet-pane')", 30), 'page did not load offline')
            self.assertTrue(until(pg, "() => document.querySelectorAll('#map img.leaflet-tile-loaded').length >= 4", 30), pg.evaluate(STATE))
            pg.wait_for_timeout(2000)
            self.assertEqual(len(navs) - n, 1, 'offline visit reloaded again')
            os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, 'healed_offline.png'))
            b.close()

    def test_heal_then_osm_blocked_in_worker_switches_to_openfreemap(self):
        """(3): worker ON, OSM refused for page and worker fetches; the backup draws and the page keeps responding."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            blocker = "const __f=self.fetch;self.fetch=function(r,o){var u=typeof r==='string'?r:r.url;return /tile\\.openstreetmap\\.org/.test(u)?Promise.reject(new TypeError('blocked by test')):__f.call(self,r,o)};\n"
            b, c, holder = self._ctx(p, sw_body=(blocker + open(os.path.join(R, 'sw.js'), encoding='utf-8').read()).encode())
            c.route('**://tile.openstreetmap.org/**', lambda r: r.abort('connectionrefused'))
            c.route('**://*.openfreemap.org/**', lambda r: r.fulfill(status=200, content_type='application/json', body=OFM,
                                                                         headers={'access-control-allow-origin': '*'}) if '/styles/' in r.request.url
                    else r.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'}))
            pg = c.new_page()
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
            self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller", 20), 'worker not on')
            pg.reload(wait_until='load')
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='openfreemap' && !!document.querySelector('#map canvas.maplibregl-canvas, #map .maplibregl-canvas')", 40),
                            pg.evaluate(STATE))
            fo = pg.evaluate('() => window.TILE_FAILOVER')
            self.assertEqual((fo['from'], fo['to']), ('osm', 'openfreemap'))
            gaps = pg.evaluate("""() => new Promise(done => { let last = performance.now(), worst = 0, n = 0;
              const t = setInterval(() => { const now = performance.now(); worst = Math.max(worst, now - last); last = now;
                if (++n === 30) { clearInterval(t); done(worst) } }, 100); })""")
            self.assertLess(gaps, 1000, 'main thread froze %dms' % gaps)
            pg.evaluate("() => map.setView([53.48, -2.24], 7)"); pg.wait_for_timeout(800)
            self.assertEqual(pg.evaluate('() => window.TILE_ACTIVE'), 'openfreemap')
            os.makedirs(SHOTS, exist_ok=True); pg.screenshot(path=os.path.join(SHOTS, 'sw_on_osm_blocked_backup.png'))
            b.close()

    def test_clean_phone_never_reloads(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b, c, _ = self._ctx(p)
            c.route('**://tile.openstreetmap.org/**', png)
            pg = c.new_page(); pg.goto(BASE + '/?nocount', wait_until='load')
            self.assertTrue(until(pg, PAINTED, 30), pg.evaluate(STATE))
            self.assertIsNone(pg.evaluate("() => sessionStorage.getItem('hmHealOld')"))
            b.close()


del IPhone  # run its tests once, in test_iphone_map_fix
if __name__ == '__main__': unittest.main()
