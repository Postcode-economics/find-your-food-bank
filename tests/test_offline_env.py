"""Local checks stay on this checkout, and an offline reload runs the layers.js this build caches."""
import os
import re
import sys
import unittest

R = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import check_browser as B
import offline_env

OLD_LAYERS = 'layers.js?v=v1792959725'
CH = '/usr/bin/google-chrome'


class Wiring(unittest.TestCase):
    def test_refuses_a_remote_url(self):
        self.assertEqual(offline_env.main(['offline_env.py', 'journeys', 'https://helpmap.uk']), 2)
        self.assertEqual(offline_env.main(['offline_env.py', 'https://helpmap.uk']), 2)
        self.assertEqual(offline_env.main(['offline_env.py']), 2)

    def test_tile_hosts_match_and_the_site_does_not(self):
        self.assertTrue(offline_env.is_tile('https://tile.openstreetmap.org/6/31/20.png'))
        self.assertTrue(offline_env.is_tile('https://a.tile.openstreetmap.org/1/0/0.png'))
        self.assertTrue(offline_env.is_tile('https://api.maptiler.com/maps/streets-v2/256/6/31/20.png?key=abc'))
        self.assertTrue(offline_env.is_tile('https://tiles.stadiamaps.com/tiles/osm_bright/1/0/0.png'))
        self.assertTrue(offline_env.is_tile('https://tiles.openfreemap.org/styles/positron'))
        self.assertFalse(offline_env.is_tile('https://helpmap.uk/icon-192.png'))
        self.assertFalse(offline_env.is_tile('https://api.postcodes.io/postcodes/SW1A1AA'))

    def test_checks_stub_tiles_and_do_not_name_the_live_site(self):
        browser = open(os.path.join(R, 'scripts', 'check_browser.py'), encoding='utf-8').read()
        self.assertIn('stub_map_tiles(c)', browser)
        self.assertIn('HELPMAP_OFFLINE_TILES', browser)
        self.assertNotIn('offline_env.install', browser)
        self.assertNotIn('host-resolver-rules', browser)
        runner = open(os.path.join(R, 'scripts', 'offline_env.py'), encoding='utf-8').read()
        self.assertNotIn('~NOTFOUND', runner)
        old = open(os.path.join(R, 'scripts', 'old_links.py'), encoding='utf-8').read()
        self.assertEqual(old.count('stub_map_tiles(c)'), 2)  # after the catch-all, and again after unroute
        ready = open(os.path.join(R, 'tests', 'site_ready.py'), encoding='utf-8').read()
        self.assertEqual(ready.count('stub_map_tiles(page)'), 2)
        self.assertEqual(ready.count('wait_until="domcontentloaded"'), 2)

    def test_layers_query_moved_off_the_old_shared_cache_key(self):
        html = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        m = re.search(r'layers\.js\?v=[A-Za-z0-9]+', html)
        self.assertTrue(m, 'index.html has no versioned layers.js')
        self.assertNotEqual(m.group(0), OLD_LAYERS)
        self.assertIn(m.group(0), sw)
        self.assertNotIn(OLD_LAYERS, sw)
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        self.assertNotIn('xl3BtUpxQak69583G9Q6', tiles)
        self.assertIn("key: ''", tiles)
        self.assertIn('disabled: true', tiles)
        self.assertLess(tiles.find("name: 'osm'"), tiles.find("name: 'openfreemap'"))
        self.assertLess(tiles.find("name: 'openfreemap'"), tiles.find("name: 'maptiler'"))


class OfflineReload(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(CH), 'needs chrome')
    def test_offline_reload_runs_the_cached_layers_build(self):
        import functools
        import http.server
        import threading
        from playwright.sync_api import sync_playwright
        html = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        layers_url = re.search(r'layers\.js\?v=[A-Za-z0-9]+', html).group(0)
        cache_name = re.search(r"const C='([^']+)'", sw).group(1)
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
        h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
        real = []
        try:
            with sync_playwright() as p:
                # This one launch only. A service-worker fetch can miss the route and
                # would otherwise pan a tile host. The shared browser setup does not
                # set this: HELPMAP_OFFLINE_TILES must still reach its tileserver.
                b = p.chromium.launch(executable_path=CH, args=[
                    '--host-resolver-rules=' + ', '.join(
                        'MAP %s ~NOTFOUND' % h for h in (
                            'tile.openstreetmap.org', 'a.tile.openstreetmap.org',
                            'b.tile.openstreetmap.org', 'c.tile.openstreetmap.org',
                            'api.maptiler.com', 'tiles.stadiamaps.com', 'tiles.openfreemap.org'))])
                c = b.new_context(viewport={'width': 390, 'height': 844}, service_workers='allow',
                                  user_agent=B.DESK_UA)
                B.stub_map_tiles(c)
                pg = c.new_page()
                pg.set_default_timeout(120000)

                def _resp(res):
                    # A 200 without the stub header is a real tile host. A DNS failure is the backstop.
                    if offline_env.is_tile(res.url) and res.status == 200 and res.headers.get('x-helpmap-tile') != 'stub':
                        real.append(res.url)
                pg.on('response', _resp)
                pg.goto(base + '/index.html?nocount', wait_until='domcontentloaded')
                pg.evaluate("""async () => {
                  await navigator.serviceWorker.ready;
                  if (navigator.serviceWorker.controller) return;
                  await new Promise(res => {
                    navigator.serviceWorker.addEventListener('controllerchange', () => res(), {once: true});
                    if (navigator.serviceWorker.controller) res();
                  });
                }""")
                state = pg.evaluate("""async (spec) => {
                  const layers = spec.layers;
                  const cache = await caches.open(spec.cache);
                  const keys = (await cache.keys()).map(k => k.url);
                  const hit = keys.find(u => u.includes(layers));
                  let body = '';
                  if (hit) body = await (await cache.match(hit)).text();
                  return {controller: !!navigator.serviceWorker.controller, hit: hit || '', london: body.includes('function london'),
                          today: body.includes('Updated today at'), keys: keys.filter(u => u.includes('layers.js'))};
                }""", {'layers': layers_url, 'cache': cache_name})
                self.assertTrue(state['controller'], state)
                self.assertIn(layers_url, state['hit'], state)
                self.assertTrue(state['london'], state)
                self.assertFalse(state['today'], state)
                c.set_offline(True)
                pg.reload(wait_until='domcontentloaded')
                got = pg.evaluate("""(layers) => {
                  const src = [...document.scripts].map(s => s.src).find(s => s.includes('layers.js')) || '';
                  const n = (window.FB_DATA && FB_DATA.items && FB_DATA.items.length) || 0;
                  return {src, n, pane: !!document.querySelector('#map .leaflet-pane'),
                          q: !!document.querySelector('#q'),
                          checked: !!(window.FB_STAMP && FB_STAMP.checked && FB_STAMP.checked.label)};
                }""", layers_url)
                self.assertIn(layers_url, got['src'], got)
                self.assertNotIn(OLD_LAYERS, got['src'], got)
                self.assertGreater(got['n'], 100, got)
                self.assertTrue(got['pane'] and got['q'], got)
                self.assertTrue(got['checked'], got)
                self.assertEqual(real, [], real[:5])
                b.close()
        finally:
            srv.shutdown()


if __name__ == '__main__':
    unittest.main()
