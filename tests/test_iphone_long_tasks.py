"""iPhone 13, WebKit, 4x CPU: grouping the food-bank pins must keep yielding.

27 Oct 2026. On a throttled phone the cluster plugin only checked the clock every
200 markers, so each slice ran 1.1–1.3s and taps did nothing until it finished.
The boot task that parses data.js is not this test: only gaps that start at or
after map.addLayer and before the first pin are. A gap under 50ms is a yield.
"""
import os, subprocess, time, unittest
R = os.path.join(os.path.dirname(__file__), '..')
BASE = 'https://helpmap.uk'
CG = '/sys/fs/cgroup/hmthrottle'
LIMIT_MS = 450  # a slice longer than this is the freeze (measured 1100–1307ms before the fix)

def _cgroup_ok():
    try:
        subprocess.run(['sudo', 'mkdir', '-p', CG], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['sudo', 'tee', CG + '/cpu.max'], input=b'25000 100000\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['sudo', 'tee', CG + '/cpu.max.burst'], input=b'0\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

HAVE_CG = _cgroup_ok()

def _webkit_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.webkit.launch(); b.close()
        return True
    except Exception:
        return False

HAVE_WEBKIT = _webkit_ok()

INIT = r"""
(() => {
  const gaps = [];
  let last = performance.now();
  setInterval(() => {
    const n = performance.now();
    const d = n - last;
    if (d >= 50) gaps.push([Math.round(d), Math.round(n)]);
    last = n;
  }, 16);
  window.__hmGaps = gaps;
  const watch = () => {
    if (window.__pinsAt) return;
    if (document.querySelector('.leaflet-marker-icon')) window.__pinsAt = performance.now();
  };
  new MutationObserver(watch).observe(document, {childList: true, subtree: true});
})();
"""

def _web_pids():
    out = subprocess.check_output(['ps', '-eo', 'pid,args'], text=True)
    return [int(l.split(None, 1)[0]) for l in out.splitlines() if 'WPEWebProcess' in l]

def _self_procs():
    path = ''
    for line in open('/proc/self/cgroup'):
        path = line.strip().split(':', 2)[-1]
    return '/sys/fs/cgroup' + path + '/cgroup.procs'

def _move(pid, dest):
    subprocess.run(['sudo', 'tee', dest], input=('%d\n' % pid).encode(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class T(unittest.TestCase):
    def test_cluster_slices_are_configured(self):
        # CI has no WebKit. These strings are what makes the throttled phone yield.
        html = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        src = open(os.path.join(R, 'vendor', 'leaflet.markercluster.js'), encoding='utf-8').read()
        self.assertIn('chunkInterval:40', html)
        self.assertIn('chunkDelay:0', html)
        self.assertIn('p-s>=32)break', src)
        self.assertNotIn('p%200==0', src)

    @unittest.skipUnless(HAVE_WEBKIT, 'needs playwright webkit')
    @unittest.skipUnless(HAVE_CG, 'needs a cgroup cpu.max of 25ms/100ms (4x)')
    def test_iphone_cluster_slices_stay_short(self):
        import mimetypes, sys
        sys.path.insert(0, os.path.join(R, 'scripts'))
        from playwright.sync_api import sync_playwright
        import check_browser as B

        def local(route):
            url = route.request.url
            if not url.startswith(BASE):
                return route.fallback()
            path = url.split(BASE, 1)[1].split('?', 1)[0].split('#', 1)[0] or '/'
            if path == '/sw.js':
                # Precache install is a separate stall. This test measures clustering only.
                body = b"self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));"
                return route.fulfill(status=200, body=body, headers={'content-type': 'text/javascript', 'cache-control': 'no-store'})
            f = os.path.join(R, path.lstrip('/'))
            if os.path.isdir(f):
                f = os.path.join(f, 'index.html')
            if not os.path.isfile(f):
                return route.fulfill(status=404, body=b'')
            raw = open(f, 'rb').read()
            headers = {'cache-control': 'no-store', 'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream'}
            if f.endswith('index.html'):
                text = raw.decode('utf-8')
                needle = 'map.addLayer(cl);'
                if text.count(needle) != 1:
                    raise AssertionError('map.addLayer(cl) count %s' % text.count(needle))
                text = text.replace(needle, "performance.mark('hm-cluster');" + needle, 1)
                raw = text.encode()
                headers['content-type'] = 'text/html'
            route.fulfill(status=200, body=raw, headers=headers)

        pid = None
        with sync_playwright() as p:
            device = dict(p.devices['iPhone 13'])
            device.pop('default_browser_type', None)
            before = set(_web_pids())
            b = p.webkit.launch()
            try:
                ctx = b.new_context(**device)
                ctx.add_init_script(INIT)
                ctx.route(BASE + '/**', local)
                ctx.route(BASE + '/', local)
                B.stub_map_tiles(ctx)
                pg = ctx.new_page()
                pg.goto('about:blank')
                pg.wait_for_timeout(300)
                new = [x for x in _web_pids() if x not in before] or _web_pids()
                self.assertTrue(new, 'no WPEWebProcess to throttle')
                pid = max(new)
                _move(pid, CG + '/cgroup.procs')
                loop = pg.evaluate("() => { let x=0; const t=performance.now(); for (let i=0;i<800000000;i++) x=(x+i)|0; return Math.round(performance.now()-t); }")
                # Unthrottled this loop is ~209ms. Under 500ms means the 4x cap is not on this process.
                self.assertGreaterEqual(loop, 500, 'calibration loop %sms, want >=500 under 4x' % loop)
                pg.goto(BASE + '/?nocount', wait_until='load', timeout=120000)
                deadline = time.time() + 60
                while time.time() < deadline:
                    if pg.evaluate("() => !!(window.__pinsAt && performance.getEntriesByName('hm-cluster').length)"):
                        break
                    pg.wait_for_timeout(100)
                info = pg.evaluate("""() => {
                  const mark = performance.getEntriesByName('hm-cluster')[0];
                  return {mark: mark ? mark.startTime : null, pinsAt: window.__pinsAt || null,
                    gaps: window.__hmGaps || [], items: (typeof items === 'undefined' ? 0 : items.length),
                    pins: document.querySelectorAll('.leaflet-marker-icon').length};
                }""")
            finally:
                b.close()
                if pid:
                    try: _move(pid, _self_procs())
                    except Exception: pass
        self.assertIsNotNone(info['mark'], info)
        self.assertIsNotNone(info['pinsAt'], info)
        self.assertGreater(info['items'], 1000, info)
        self.assertGreater(info['pins'], 0, info)
        mark, pins_at = info['mark'], info['pinsAt']
        cluster = []
        covering = 0
        for ms, at in info['gaps']:
            start = at - ms
            if start >= mark and start < pins_at:
                cluster.append(ms)
            elif start < mark <= at:
                covering = max(covering, at - mark)
        worst = max(cluster) if cluster else covering
        print('cluster slice %sms loop %sms gaps %s boot overrun %.0f mark %.0f pins %.0f' % (
            round(worst), loop, cluster, covering, mark, pins_at))
        self.assertLess(worst, LIMIT_MS, 'longest cluster slice %sms (gaps %s, boot overrun %.0f, mark %.0f, pins %.0f, loop %sms)' % (
            round(worst), cluster, covering, mark, pins_at, loop))
