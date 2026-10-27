"""iPhone map freeze (ANGLE D, 27 Oct 2026).

WebKit has no Performance longtask entries, so a 50 ms timer heartbeat measures main-thread gaps
(a gap is a task that ran longer than the interval). A tap is the time from pointerdown to click.

Two freezes this file locks out:

1. Self-heal and the boot watchdog reloaded with location.reload() after writing sessionStorage.
   In a webview where getItem always returns null and setItem does not throw (storage that does
   not survive a reload), and version.json names a different build, that reload never stops.
   The guard is a hmheal=1 / hmboot=1 flag written with history.replaceState before the reload.
   If the flag cannot be written, the page does not reload. A throwing sessionStorage still
   skips the reload, because setItem stays outside try.

2. The OpenFreeMap backup (MapLibre) could leave the map dead without falling back: the worker
   URL was relative, the WebGL probe context was never released, phones built the canvas at
   pixel ratio 2, TILE_VECTOR was set to ready before the style loaded, and a lost WebGL context
   had no listener. The 3-in-20 refusal rule is not changed.

Fails when any heartbeat gap is over 1s, or a tap is not handled within TAP_MS.
WebKit iPhone 13 and iPhone SE, service worker on and off, through load, Locate, Find nearest,
the switch to the backup and the fall back to OpenStreetMap. Stand-in tiles only.
"""
import hashlib, json, mimetypes, os, subprocess, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import check_browser as B

BASE = 'https://helpmap.uk'
LONG_MS = 1000
TAP_MS = 2000
CASE_LIMIT_S = 150
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
FLOW = ('13-off', '13-on', 'se-off', 'se-on')
HEAL = ('heal-13', 'heal-se')
DEVICES = {'13': 'iPhone 13', 'se': 'iPhone SE'}
PROBE = """(() => {
  if (window.__hb) return;
  window.__hb = {last: performance.now(), max: 0, n: 0};
  setInterval(() => {
    const t = performance.now(), g = t - window.__hb.last;
    window.__hb.last = t; window.__hb.n++;
    if (g > window.__hb.max) window.__hb.max = g;
  }, 50);
  window.__tap = {t0: 0, ms: 0, max: 0, n: 0};
  addEventListener('pointerdown', () => { window.__tap.t0 = performance.now(); }, true);
  addEventListener('click', () => {
    if (!window.__tap.t0) return;
    const d = performance.now() - window.__tap.t0;
    window.__tap.ms = d; window.__tap.n++;
    if (d > window.__tap.max) window.__tap.max = d;
    window.__tap.t0 = 0;
  }, true);
})()"""
WIPE = """(() => {
  const mem = {};
  const fake = {
    getItem(k) { return (k === 'hmHeal' || k === 'hmBoot') ? null : (Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null); },
    setItem(k, v) { if (k === 'hmHeal' || k === 'hmBoot') return; mem[k] = String(v); },
    removeItem(k) { delete mem[k]; },
    clear() { for (const k of Object.keys(mem)) delete mem[k]; },
    key(i) { return Object.keys(mem)[i] || null; },
    get length() { return Object.keys(mem).length; }
  };
  Object.defineProperty(window, 'sessionStorage', { configurable: true, get() { return fake; } });
})()"""


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def _read(f):
    with open(f, 'rb') as fh:
        return fh.read()


def until(pg, js, secs=25):
    for _ in range(int(secs * 4)):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


def local_file(route):
    path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
    f = os.path.join(R, path.lstrip('/'))
    f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
    if not os.path.isfile(f):
        return route.fulfill(status=404, body='')
    route.fulfill(status=200, body=_read(f), headers={
        'content-type': mimetypes.guess_type(f)[0] or 'text/html', 'cache-control': 'no-store'})


def sw_body():
    """Real sw.js, with tile fetches answered inside the worker.

    Playwright does not intercept a request the service worker has already taken
    (page.route never sees it), so a controlled page would otherwise hit the public
    tile servers. The worker still runs the real cache-first handler; only its
    outbound tile fetch is local. The page tells it to refuse or allow.
    """
    real = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
    return (
        "self.addEventListener('message',function(e){if(!e.data||!e.data.helpmapTest)return;"
        "self.__hmRefuse=e.data.helpmapTest==='refuse';if(e.ports&&e.ports[0])e.ports[0].postMessage(!!self.__hmRefuse)});"
        "(function(){var orig=self.fetch;self.fetch=function(input,init){var url=(typeof input==='string')?input:(input&&input.url)||'';"
        "if(/tile\\.openstreetmap\\.org|tiles\\.openfreemap\\.org|maptiler\\.com|stadiamaps\\.com/.test(url)){"
        "if(self.__hmRefuse&&/openstreetmap/.test(url))return Promise.resolve(new Response('',{status:429,headers:{'content-type':'image/png','access-control-allow-origin':'*'}}));"
        "return orig.call(self,new URL('/scripts/tile_placeholder.png',self.location).href);}"
        "return orig.apply(self,arguments)};})();\n" + real
    )


def tell_sw(pg, mode):
    pg.evaluate("""mode => { const c = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (!c) return false;
      return new Promise(res => { const ch = new MessageChannel();
        ch.port1.onmessage = () => res(true);
        c.postMessage({helpmapTest: mode}, [ch.port2]);
        setTimeout(() => res(false), 1000); }); }""", mode)


class Source(unittest.TestCase):
    def test_guards_are_in_the_source(self):
        home = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        for s in ("searchParams.set('hmheal','1')", "searchParams.set('hmboot','1')",
                  "if(!/[?&]hmheal=1(?:&|$)/.test(location.search))return",
                  "if(!/[?&]hmboot=1(?:&|$)/.test(location.search))return",
                  "sessionStorage.setItem(k,v.build)", "location.reload()", "var k='hmBoot'", "k='hmHeal'"):
            self.assertIn(s, home)
        uv = tiles.split('function useVector', 1)[1]
        self.assertLess(uv.index('setTimeout(ok, 0)'), uv.index('L.maplibreGL'))
        self.assertLess(uv.index("glMap.on('load'"), uv.index("window.TILE_VECTOR = 'ready'"))
        for s in ("new URL('vendor/maplibre-gl-csp-worker.js', location.href)", 'WEBGL_lose_context',
                  'trackResize: false', 'webglcontextlost', 'vector style timeout',
                  'return Math.min(dpr, phone ? 1 : 2);', 'window.TILE_WINDOW_REFUSALS = 3'):
            self.assertIn(s, tiles)
        q = 'tiles.js?v=h' + hashlib.sha256(tiles.encode()).hexdigest()[:12]
        self.assertIn(q, home)
        self.assertIn(q, sw)


def phase(pg, bad, name):
    hb = pg.evaluate("""() => { const max = window.__hb.max; window.__hb.max = 0;
      return {max: Math.round(max), n: window.__hb.n, tap: Math.round(window.__tap.max)}; }""")
    print(name, hb, flush=True)
    if hb['max'] > LONG_MS:
        bad.append('%s long task %d ms (over %d)' % (name, hb['max'], LONG_MS))
    return hb


def tap(pg, bad, sel, name):
    before = pg.evaluate('window.__tap.n')
    box = pg.evaluate("""sel => {
      const e = document.querySelector(sel);
      if (!e) return null;
      e.scrollIntoView({block: 'center', inline: 'nearest'});
      const r = e.getBoundingClientRect();
      return {x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height};
    }""", sel)
    if not box or box['w'] < 2 or box['h'] < 2:
        bad.append('%s not on screen %s' % (name, box))
        return
    try:
        pg.touchscreen.tap(box['x'], box['y'])
    except Exception as e:
        bad.append('%s tap failed: %s' % (name, str(e)[:140]))
        return
    if not until(pg, 'window.__tap.n > %d' % before, TAP_MS / 1000.0 + 1):
        bad.append('%s tap not handled within %d ms' % (name, TAP_MS))
        return
    ms = pg.evaluate('window.__tap.ms')
    print(name, 'tap', round(ms), flush=True)
    if ms > TAP_MS:
        bad.append('%s tap handled in %d ms (over %d)' % (name, round(ms), TAP_MS))


def run_flow(case):
    from playwright.sync_api import sync_playwright
    which, sw = case.split('-')
    device = DEVICES[which]
    bad, outside, errs = [], [], []
    mode = {'osm': 200}

    def tiles(route):
        url = route.request.url
        if 'tiles.openfreemap.org' in url:
            if '/styles/' in url or url.endswith('.json'):
                return route.fulfill(status=200, content_type='application/json', body=OFM_STYLE,
                                     headers={'access-control-allow-origin': '*'})
            return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})
        return route.fulfill(status=mode['osm'], content_type='image/png', body=B.TILE_PNG,
                             headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})

    def block(route):
        url = route.request.url
        if url.startswith(('blob:', 'data:')):
            return route.fallback()
        outside.append(url[:140])
        route.abort()

    def page(route):
        path = route.request.url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
        if sw == 'on' and path.endswith('/sw.js'):
            return route.fulfill(status=200, body=sw_body(), headers={
                'content-type': 'application/javascript', 'cache-control': 'no-store',
                'service-worker-allowed': '/'})
        return local_file(route)

    with sync_playwright() as p:
        b = p.webkit.launch()
        iphone = dict(p.devices[device])
        iphone.pop('default_browser_type', None)
        c = b.new_context(**iphone, service_workers='allow' if sw == 'on' else 'block',
                          geolocation={'latitude': 53.48, 'longitude': -2.24}, permissions=['geolocation'])
        c.add_init_script(PROBE)
        c.route('**/*', block)
        c.route('https://api.postcodes.io/**', lambda r: r.fulfill(
            status=200, content_type='application/json', body='{"status":200,"result":{}}',
            headers={'access-control-allow-origin': '*'}))
        c.route(BASE + '/**', page)
        c.route(BASE + '/', page)
        c.route(B.TILE_RE, tiles)
        pg = c.new_page()
        pg.set_default_timeout(20000)
        pg.on('pageerror', lambda e: errs.append(str(e)[:180]))
        pg.goto(BASE + '/?nocount', wait_until='domcontentloaded')
        if not until(pg, "!!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))"
                     " && document.querySelectorAll('#map .leaflet-tile-loaded').length > 3", 40):
            bad.append('map never built ' + str(pg.evaluate(
                "({a: window.TILE_ACTIVE, pane: !!document.querySelector('#map .leaflet-pane')})")))
        else:
            phase(pg, bad, 'load')
            tap(pg, bad, '#me', 'locate')
            if not until(pg, "document.querySelectorAll('#list .card').length > 0", 8):
                bad.append('Locate showed no cards ' + str(pg.evaluate("document.getElementById('msg').textContent")))
            phase(pg, bad, 'locate')
            tap(pg, bad, '#xnear', 'find-nearest')
            if not until(pg, "document.querySelectorAll('#list .card').length > 0", 8):
                bad.append('Find nearest showed no cards')
            phase(pg, bad, 'find-nearest')
            if sw == 'on' and not until(pg, '!!navigator.serviceWorker.controller', 15):
                bad.append('service worker did not take control')
            mode['osm'] = 429
            if sw == 'on':
                tell_sw(pg, 'refuse')
            pg.evaluate("map.setView([57.15, -2.09], 14, {animate: false})")
            if not until(pg, "window.TILE_ACTIVE==='openfreemap'", 20):
                pg.evaluate("map.setView([50.72, -1.88], 15, {animate: false})")
            switched = until(pg, "window.TILE_ACTIVE==='openfreemap' && window.TILE_VECTOR==='ready'"
                             " && !!document.querySelector('#map canvas')", 25)
            if not switched:
                bad.append('backup did not become ready ' + str(pg.evaluate(
                    "({a: window.TILE_ACTIVE, v: window.TILE_VECTOR || null, f: window.TILE_FAILOVER || null})")))
            else:
                ratio = pg.evaluate("""() => { const c = document.querySelector('#map canvas');
                  return {w: c.width, cw: c.clientWidth, dpr: devicePixelRatio,
                    touch: navigator.maxTouchPoints,
                    coarse: matchMedia('(hover: none) and (pointer: coarse)').matches}; }""")
                print('canvas', ratio, flush=True)
                if not ratio['cw'] or ratio['w'] > ratio['cw'] * 1.5:
                    bad.append('phone canvas pixel ratio too high %s' % ratio)
                phase(pg, bad, 'switch')
                mode['osm'] = 200
                if sw == 'on':
                    tell_sw(pg, 'allow')
                lost = pg.evaluate("""() => { const c = document.querySelector('#map canvas');
                  const gl = c.getContext('webgl2') || c.getContext('webgl');
                  if (!gl) return 'no-gl';
                  const ext = gl.getExtension('WEBGL_lose_context');
                  if (!ext) return 'no-ext';
                  ext.loseContext(); return 'lost'; }""")
                print('context', lost, flush=True)
                if lost != 'lost':
                    bad.append('could not lose webgl context (%s)' % lost)
                fell = until(pg, "window.TILE_ACTIVE==='osm' && /^failed/.test(window.TILE_VECTOR||'')", 15)
                if not fell:
                    bad.append('did not fall back after context loss ' + str(pg.evaluate(
                        "({a: window.TILE_ACTIVE, v: window.TILE_VECTOR || null})")))
                elif not until(pg, "document.querySelectorAll('#map .leaflet-tile-loaded').length > 3", 15):
                    bad.append('OpenStreetMap tiles did not return after the fall back ' + str(pg.evaluate(
                        "({a: window.TILE_ACTIVE, v: window.TILE_VECTOR || null, n: document.querySelectorAll('#map .leaflet-tile-loaded').length})")))
                phase(pg, bad, 'fallback')
                tap(pg, bad, '#chips [data-f=walk]', 'after-fallback')
                if not until(pg, "document.querySelector('#chips [data-f=walk]').getAttribute('aria-pressed')==='true'", 4):
                    bad.append('filter tap after fallback did not stick')
        if outside:
            bad.append('requests left the test: %s' % sorted(set(outside))[:6])
        surprise = [e for e in errs if not any(s in e for s in (
            'webgl context', 'Context lost', 'vector style', 'AbortError'))]
        if surprise:
            bad.append('page errors: %s' % surprise[:4])
        c.close(); b.close()
    if bad:
        raise SystemExit(case + ' FAILED\n' + '\n'.join(bad))
    print(case, 'passed', flush=True)


def run_heal(case):
    from playwright.sync_api import sync_playwright
    device = DEVICES[case.split('-')[1]]
    bad, docs = [], []

    def local(route):
        url = route.request.url
        path = url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
        if route.request.resource_type == 'document':
            docs.append(url[:160])
        if path.endswith('version.json'):
            return route.fulfill(status=200, body=b'{"build":"fyfb-v99"}',
                                 headers={'content-type': 'application/json', 'cache-control': 'no-store'})
        return local_file(route)

    with sync_playwright() as p:
        b = p.webkit.launch()
        iphone = dict(p.devices[device])
        iphone.pop('default_browser_type', None)
        c = b.new_context(**iphone, service_workers='block',
                          geolocation={'latitude': 53.48, 'longitude': -2.24}, permissions=['geolocation'])
        c.add_init_script(WIPE)
        c.add_init_script(PROBE)
        c.route(BASE + '/**', local)
        c.route(BASE + '/', local)
        c.route(B.TILE_RE, lambda r: r.fulfill(
            status=200, content_type='image/png', body=B.TILE_PNG,
            headers={'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'}))
        pg = c.new_page()
        pg.set_default_timeout(15000)
        try:
            pg.goto(BASE + '/?nocount&fresh=1', wait_until='domcontentloaded')
        except Exception as e:
            print('goto', str(e)[:160], flush=True)
        settled = False
        for _ in range(40):
            n = len(docs)
            pg.wait_for_timeout(400)
            if len(docs) != n:
                continue
            try:
                if pg.evaluate("!!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))"):
                    settled = True
                    break
            except Exception:
                pass
        print('navs', len(docs), docs[:8], flush=True)
        if len(docs) > 2:
            bad.append('self-heal reload loop: %d document loads %s' % (len(docs), docs[:6]))
        if not settled:
            bad.append('page never settled after self-heal (%d loads)' % len(docs))
        else:
            href = pg.evaluate('location.href')
            if 'hmheal=1' not in href:
                bad.append('reload did not keep hmheal=1 (%s)' % href)
            phase(pg, bad, 'heal-load')
            tap(pg, bad, '#me', 'heal-locate')
            if not until(pg, "document.querySelectorAll('#list .card').length > 0", 8):
                bad.append('tap after self-heal was not handled ' + str(pg.evaluate(
                    "document.getElementById('msg') && document.getElementById('msg').textContent")))
        # One quiet second: a loop that survived the first settle would navigate again.
        n = len(docs)
        pg.wait_for_timeout(1000)
        if len(docs) != n:
            bad.append('kept reloading after settle (%d -> %d)' % (n, len(docs)))
        c.close(); b.close()
    if bad:
        raise SystemExit(case + ' FAILED\n' + '\n'.join(bad))
    print(case, 'passed', flush=True)


class IPhoneFreeze(unittest.TestCase):
    def guarded(self, case):
        pr = subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), case], cwd=R, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = pr.communicate(timeout=CASE_LIMIT_S)
        except subprocess.TimeoutExpired:
            os.killpg(pr.pid, 9)
            out, err = pr.communicate()
            self.fail('%s froze, no answer within %d s\n%s' % (case, CASE_LIMIT_S, (out or '')[-800:]))
        print((out or '')[-600:])
        self.assertEqual(pr.returncode, 0, '%s failed:\n%s%s' % (case, (out or '')[-2000:], (err or '')[-2000:]))

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_iphone_13_service_worker_off(self):
        self.guarded('13-off')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_iphone_13_service_worker_on(self):
        self.guarded('13-on')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_iphone_se_service_worker_off(self):
        self.guarded('se-off')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_iphone_se_service_worker_on(self):
        self.guarded('se-on')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_self_heal_does_not_reload_loop_iphone_13(self):
        self.guarded('heal-13')

    @unittest.skipUnless(HAVE, 'needs playwright webkit')
    def test_self_heal_does_not_reload_loop_iphone_se(self):
        self.guarded('heal-se')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] in FLOW + HEAL:
        import warnings
        warnings.simplefilter('ignore', ResourceWarning)
        (run_heal if sys.argv[1] in HEAL else run_flow)(sys.argv[1])
    else:
        unittest.main()
