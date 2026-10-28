"""iPhone boot must not freeze the main thread (27 Oct 2026).

Profiled on WebKit, Playwright's iPhone 13 device, renderer held to a 25% duty
cycle (4x): the parser ran data.js, Leaflet and the inline boot as one turn.
The longest frame gap was 669ms with the service worker blocked and 818ms with
it running. The inline boot alone was ~496ms, of which marker clustering on
map.addLayer was 164ms. This file locks the yield: the heavy scripts are not
parser-blocking, and clustering runs on a later turn.

The WebKit timing check is skipped when Playwright WebKit is not installed
(the plain pytest job). The source checks always run, and they fail on a page
that still parser-blocks data.js.
"""
import mimetypes, os, signal, sys, threading, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import check_browser as B
R = os.path.join(os.path.dirname(__file__), '..')
# Before this change the longest 4x frame gap was 888ms in this harness, and 669ms
# (service worker blocked) / 818ms (worker running) in the earlier profile.
# After the yield the same harness measured 327–422ms. Stay under the old floor.
MAX_GAP_MS = 560
RUN_MS = 20
CHAIN = ['data.js', 'stamp.js', 'access.js', 'vendor/leaflet.js', 'vendor/leaflet.markercluster.js',
         'tiles.js', 'boot', 'layers.js', 'report.js', 'register.js', 'v3.js', 'showmore.js']  # main's show-more (#212) also waits for v3.js

def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False
HAVE = have_webkit()

class Scripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from html.parser import HTMLParser
        class P(HTMLParser):
            def __init__(self):
                super().__init__(); self.scripts = []; self._cur = None
            def handle_starttag(self, tag, attrs):
                self._cur = None
                if tag != 'script': return
                self._cur = {'attrs': dict(attrs), 'data': ''}; self.scripts.append(self._cur)
            def handle_endtag(self, tag):
                if tag == 'script': self._cur = None
            def handle_data(self, data):
                if self._cur is not None: self._cur['data'] += data
        with open(os.path.join(R, 'index.html'), encoding='utf-8') as fh: cls.html = fh.read()
        cls.p = P(); cls.p.feed(cls.html)

    def test_boot_scripts_are_not_parser_blocking(self):
        names = []
        for s in self.p.scripts:
            if 'data-hm' not in s['attrs']: continue
            src = s['attrs'].get('src') or ''
            names.append(src.split('?')[0] if src else 'boot')
            self.assertEqual(s['attrs'].get('type'), 'text/plain', src or 'boot')
        self.assertEqual(names, CHAIN)
        for s in self.p.scripts:
            src = s['attrs'].get('src') or ''
            if src.split('?')[0] in ('data.js', 'vendor/leaflet.js', 'layers.js', 'v3.js'):
                self.assertEqual(s['attrs'].get('type'), 'text/plain', src)

    def test_clustering_yields_and_search_cannot_reload(self):
        boots = [s for s in self.p.scripts if s['attrs'].get('id') == 'hm-boot']
        self.assertEqual(len(boots), 1)
        boot = boots[0]
        self.assertIn('function refreshClusters()', boot['data'])
        self.assertIn('setTimeout(', boot['data'])
        self.assertIn('cl.addLayers(', boot['data'])
        self.assertIn('map.addLayer(cl)', boot['data'])
        self.assertNotIn('cl.addLayer(m)', boot['data'])
        self.assertIn('chunkInterval:40', boot['data'])  # #178 yields every 32 markers; it supersedes the 1e9 chunk
        self.assertIn("__hmPendingSearch", boot['data'])
        self.assertIn('window.__hmPendingSearch=qs.get', boot['data'])
        self.assertNotIn('search(qs.get', boot['data'])  # v3 wraps nearest; search runs after that script
        loaders = [s for s in self.p.scripts if 'script[data-hm]' in s['data']]
        self.assertEqual(len(loaders), 1)
        loader = loaders[0]
        self.assertNotEqual(loader['attrs'].get('type'), 'text/plain')
        self.assertIn('function later(fn){requestAnimationFrame(function(){setTimeout(fn,0)})}', loader['data'])
        self.assertIn('later(run)', loader['data'])
        self.assertIn('preventDefault', loader['data'])
        self.assertIn('__hmPendingSearch', loader['data'])
        self.assertIn('search(q)', loader['data'])
        # the sheet still needs a non-passive touchmove so a drag can cancel page scroll
        self.assertIn("addEventListener('touchmove',e=>move(e.touches[0].clientY,e),{passive:false})", boot['data'])

def _web_pids():
    pids = []
    for d in os.listdir('/proc'):
        if not d.isdigit(): continue
        try:
            with open('/proc/%s/comm' % d) as fh: comm = fh.read().strip()
        except OSError: continue
        if comm.startswith('WPEWebProcess'): pids.append(int(d))
    return pids

class _Throttle:
    """Duty-cycle the WebKit renderer. Playwright has no CPU-throttle API for WebKit."""
    def __init__(self, rate=4):
        self.rate = rate; self.stop = False; self.stopped = set()
        self.thread = threading.Thread(target=self._run, daemon=True)
    def start(self):
        self.thread.start()
    def _run(self):
        run_s = RUN_MS / 1000; stop_s = RUN_MS * (self.rate - 1) / 1000
        while not self.stop:
            pids = _web_pids(); time.sleep(run_s)
            if self.stop: break
            for pid in pids:
                try: os.kill(pid, signal.SIGSTOP); self.stopped.add(pid)
                except OSError: pass
            time.sleep(stop_s)
            for pid in list(self.stopped):
                try: os.kill(pid, signal.SIGCONT)
                except OSError: pass
            self.stopped.clear()
    def close(self):
        self.stop = True
        if self.thread.is_alive(): self.thread.join(timeout=2)
        for pid in list(self.stopped) + _web_pids():
            try: os.kill(pid, signal.SIGCONT)
            except OSError: pass

class WebKit(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_iphone13_4x_boot_gap(self):
        from playwright.sync_api import sync_playwright
        base = 'https://helpmap.uk'
        def local(route):
            path = route.request.url.split(base, 1)[1].split('?')[0].split('#')[0] or '/'
            f = os.path.join(R, path.lstrip('/')); f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f): return route.fulfill(status=404, body='')
            with open(f, 'rb') as fh: body = fh.read()
            route.fulfill(status=200, body=body, headers={'content-type': mimetypes.guess_type(f)[0] or 'text/html', 'cache-control': 'no-store'})
        calib_js = "() => { const t0 = performance.now(); let x = 0; for (let i = 0; i < 120000000; i++) x = (x + i) | 0; return Math.round(performance.now() - t0); }"
        ready_js = "() => !!(window.FB_DATA && FB_DATA.items && FB_DATA.items.length > 100 && document.querySelector('#map .leaflet-marker-icon, #map .marker-cluster'))"
        th = _Throttle(4); th.start()
        try:
            with sync_playwright() as p:
                dev = dict(p.devices['iPhone 13']); dev.pop('default_browser_type', None)
                b = p.webkit.launch()
                c = b.new_context(**dev, service_workers='block')
                c.add_init_script("""window.__hmGaps=[]; let last=0; const frame=t=>{ if(last){ const d=t-last; if(d>120) window.__hmGaps.push(Math.round(d)); } last=t; requestAnimationFrame(frame); }; requestAnimationFrame(frame);""")
                c.route(base + '/**', local); c.route(base + '/', local)
                B.stub_map_tiles(c)
                pg = c.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
                pg.goto('about:blank')
                calib = pg.evaluate(calib_js)
                pg.goto(base + '/?nocount', wait_until='commit', timeout=60000)
                ready = False
                for _ in range(80):
                    try:
                        if pg.evaluate(ready_js): ready = True; break
                    except Exception: pass
                    pg.wait_for_timeout(500)
                pg.wait_for_timeout(800)
                gaps = pg.evaluate("() => window.__hmGaps || []")
                c.close(); b.close()
        finally:
            th.close()
        self.assertLess(MAX_GAP_MS, 669)  # unfixed page: 669ms with the worker blocked, 888ms in this harness
        self.assertGreaterEqual(calib, 60, 'renderer was not at 4x (calib %sms)' % calib)
        self.assertTrue(ready, 'markers never appeared; errors %s' % errs[:3])
        self.assertEqual(errs, [])
        worst = max(gaps) if gaps else 0
        print('iphone13 4x calib %sms worst gap %sms gaps %s' % (calib, worst, sorted(gaps, reverse=True)[:8]))
        self.assertLess(worst, MAX_GAP_MS, 'longest frame gap %sms at 4x (gaps %s)' % (worst, sorted(gaps, reverse=True)[:8]))

if __name__ == '__main__':
    unittest.main()
