"""Service-worker freshness (Dean, 26 Oct 2026): a returning visitor must get the new HTML and data after a deploy,
and with the network cut the last saved copy must still load the map and listings.

A copy of this checkout is served on 127.0.0.1 with HTTP caching off. Tile hosts get a blank PNG and every other
outside host is aborted (rule 23), so nothing is requested from helpmap.uk or a map server.
1. First visit: the worker installs and saves the site.
2. "Deploy": index.html, data.js (same ?v= stamp, the worst case) and report.js change on the server; version.json does
   not, so the index.html self-heal cannot hide a stale worker. A returning visit must show all three new copies.
3. Network cut: the page must still load from the saved copy, with the listings and the map.
"""
import http.server, os, re, shutil, tempfile, threading, unittest
from urllib.parse import urlparse
R = os.path.join(os.path.dirname(__file__), '..')
import sys
sys.path.insert(0, os.path.join(R, 'scripts'))
try:
    from playwright.sync_api import sync_playwright
    HAVE = True
except Exception:
    HAVE = False
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
       b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
TILE_HOSTS = ('tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com')
PROBE = "() => ({html: (document.querySelector('meta[name=deploy-probe]')||{}).content||'', data: window.__deployData||'', rep: window.__deployRep||'', n: (window.FB_DATA&&FB_DATA.items&&FB_DATA.items.length)||0, pane: !!document.querySelector('#map .leaflet-pane'), cards: document.querySelectorAll('#list .card').length})"


class Static(unittest.TestCase):
    def test_only_version_stamped_files_are_cache_first(self):
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        self.assertIn("if(/(^|&)v=/.test(u.search.slice(1)))", sw)
        self.assertIn("e.respondWith(fetch(new Request(e.request,{cache:'no-cache'})).then(put).catch(", sw)
        self.assertNotIn("if(hit){e.waitUntil(net", sw)  # old stale-while-revalidate is gone
        self.assertIn('self.skipWaiting()', sw)
        self.assertIn('self.clients.claim()', sw)


def _ignore(d, names):
    return [n for n in names if n in ('.git', 'logs', 'reports', 'tests', 'scripts', 'docs', 'export')]


class Browser(unittest.TestCase):
    def test_returning_visitor_gets_new_deploy_and_offline_copy_still_works(self):
        if not HAVE:
            self.skipTest('needs playwright')
        import check_browser as B
        tmp = tempfile.mkdtemp()
        site = os.path.join(tmp, 'site')
        shutil.copytree(R, site, ignore=_ignore)

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=site, **k)

            def end_headers(self):
                self.send_header('Cache-Control', 'no-store')
                super().end_headers()

            def log_message(self, *a):
                pass

        httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/?nocount' % httpd.server_address[1]
        leaked = []

        def handle(route):
            host = urlparse(route.request.url).hostname or ''
            if host in TILE_HOSTS or host.endswith('.tile.openstreetmap.org'):
                route.fulfill(status=200, body=PNG, headers={'content-type': 'image/png', 'access-control-allow-origin': '*'})
            elif host not in ('127.0.0.1', 'localhost'):
                leaked.append(host)
                route.abort()
            else:
                route.continue_()

        def deploy():
            p = os.path.join(site, 'index.html')
            s = open(p, encoding='utf-8').read()
            open(p, 'w', encoding='utf-8').write(s.replace('<head>', '<head><meta name="deploy-probe" content="new">', 1))
            for f, v in (('data.js', '__deployData'), ('report.js', '__deployRep')):
                with open(os.path.join(site, f), 'a', encoding='utf-8') as fh:
                    fh.write('\n;window.%s="new";\n' % v)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                ctx = B.new_context(browser, viewport={'width': 390, 'height': 844}, service_workers='allow')
                ctx.route('**/*', handle)
                pg = ctx.new_page()
                B.goto(pg, base, log=lambda *a: None)
                pg.wait_for_function("async () => { const r = await navigator.serviceWorker.getRegistration(); if (!r || !navigator.serviceWorker.controller) return false;"
                                     " const ks = await caches.keys(); for (const k of ks) { const c = await caches.open(k); if ((await c.keys()).some(x => /\\/data\\.js/.test(x.url))) return true } return false }", timeout=30000)
                pg.reload(); B.goto(pg, base, log=lambda *a: None)
                before = pg.evaluate(PROBE)
                self.assertEqual((before['html'], before['data'], before['rep']), ('', '', ''), before)
                self.assertTrue(pg.evaluate("!!navigator.serviceWorker.controller"))

                deploy()
                pg2 = ctx.new_page()
                B.goto(pg2, base, log=lambda *a: None)
                after = pg2.evaluate(PROBE)
                self.assertEqual((after['html'], after['data'], after['rep']), ('new', 'new', 'new'),
                                 'returning visitor got a stale copy after a deploy: %r' % after)
                self.assertTrue(pg2.evaluate("!!navigator.serviceWorker.controller"))

                ctx.set_offline(True)
                pg3 = ctx.new_page()
                B.goto(pg3, base, log=lambda *a: None)
                off = pg3.evaluate(PROBE)
                self.assertGreater(off['n'], 100, off)
                self.assertTrue(off['pane'], off)
                self.assertEqual((off['html'], off['data']), ('new', 'new'), off)  # the last saved copy is the new one
                ctx.set_offline(False)
                browser.close()
        finally:
            httpd.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(leaked, [], leaked)


if __name__ == '__main__':
    unittest.main()
