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


from test_iphone_map_fix import HAVE, IPhone, BASE, png, old_sw, until, PAINTED, STATE


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class StaleWorker(IPhone):
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
