"""WebKit regression: the OpenFreeMap backup must paint vector tiles on iPhone.

iOS Safari throws SyntaxError "The string did not match the expected pattern" from
new Worker(relativeUrl). MapLibre then creates a canvas and (before this fix) reported
TILE_VECTOR ready, but it never requests a .pbf, so the backup stays grey. Playwright's
WebKit build accepts a relative worker URL, so the page installs the iOS throw. The
worker URL has to be absolute or the backup cannot draw.

Scenario (Dean, 27 Oct 2026, live iPhone): the map loads on OpenStreetMap, then OSM
returns 429. Press Locate, then Find nearest. Within PAINT_S the backup must request
real vector tiles (not a GeoJSON stand-in) and paint them.

Rule 23: every tile, style and vector response is a stand-in. With the service worker
on, Playwright WebKit does not intercept fetches the worker makes, so the served sw.js
answers OSM itself (200, then 429 after a message) and never calls fetch for those tiles.
OpenFreeMap is cross-origin, so the worker does not handle it and the stand-in route does.
"""
import base64, hashlib, json, mimetypes, os, sys, unittest
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
BASE = 'https://helpmap.uk'
PAINT_S = 15
PNG = open(os.path.join(R, 'scripts', 'tile_placeholder.png'), 'rb').read()
# One Mapbox vector tile: a polygon that covers the tile in source-layer "water".
PBF = base64.b64decode('GjQKBXdhdGVyEhYSAgAAGAMiDgkAABqAQAAAgED/PwAPGgVjbGFzcyIHCgVvY2VhbiiAIHgC')
STYLE = ('{"version":8,"glyphs":"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",'
         '"sprite":"https://tiles.openfreemap.org/sprites/ofm_f384/ofm",'
         '"sources":{"openmaptiles":{"type":"vector","tiles":'
         '["https://tiles.openfreemap.org/planet/20261025_080012_pt/{z}/{x}/{y}.pbf"],'
         '"minzoom":0,"maxzoom":14}},"layers":['
         '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
         '{"id":"water","type":"fill","source":"openmaptiles","source-layer":"water",'
         '"paint":{"fill-color":"#194b7a"}}]}')
WORKER = BASE + '/vendor/maplibre-gl-csp-worker.js'
# iOS WebKit rejects a relative Worker URL with this exact SyntaxError. Absolute URLs pass.
IOS_WORKER = """(() => {
  const Native = window.Worker;
  window.Worker = function (url, opts) {
    const s = String(url && url.href || url);
    window.__hmWorkerUrl = s;
    if (!/^[a-z][a-z0-9+.-]*:/i.test(s)) {
      throw new SyntaxError('The string did not match the expected pattern.');
    }
    return new Native(s, opts);
  };
  window.__hmPbf = [];
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('message', e => {
    if (e.data && e.data.hmPbf) window.__hmPbf.push(e.data.hmPbf);
  });
})()"""
PAINT = """() => new Promise(done => {
  let lyr = null;
  if (typeof map !== 'undefined') map.eachLayer(l => { if (l.getMaplibreMap) lyr = l; });
  const gl = lyr && lyr.getMaplibreMap && lyr.getMaplibreMap();
  const snap = () => ({
    active: window.TILE_ACTIVE, v: window.TILE_VECTOR || null,
    worker: window.__hmWorkerUrl || (window.maplibregl && window.maplibregl.getWorkerUrl && window.maplibregl.getWorkerUrl()) || null,
    pbfs: (window.__hmPbf || []).concat(performance.getEntriesByType('resource').map(e => e.name).filter(n => /\\.pbf(\\?|$)/.test(n) && n.indexOf('/fonts/') < 0)),
    fo: window.TILE_FAILOVER || null, err: window.TILE_VECTOR_ERROR || null,
    canvas: !!document.querySelector('#map canvas')
  });
  if (!gl) { done(Object.assign(snap(), {water: 0, n: 0})); return; }
  let finished = false;
  const finish = () => {
    if (finished) return; finished = true;
    const out = snap();
    try {
      const cv = gl.getCanvas(), ctx = cv.getContext('webgl2') || cv.getContext('webgl');
      const buf = new Uint8Array(4); let n = 0, water = 0; const cols = {};
      const w = cv.width, h = cv.height;
      for (let i = 1; i < 6; i++) for (let j = 1; j < 6; j++) {
        ctx.readPixels((w * i / 6) | 0, (h * j / 6) | 0, 1, 1, ctx.RGBA, ctx.UNSIGNED_BYTE, buf);
        n++; cols[[...buf].join(',')] = 1;
        if (buf[0] === 25 && buf[1] === 75 && buf[2] === 122 && buf[3] === 255) water++;
      }
      out.n = n; out.water = water; out.cols = Object.keys(cols);
    } catch (e) { out.n = 0; out.water = 0; out.read = String(e).slice(0, 160); }
    done(out);
  };
  try { gl.once('render', finish); gl.triggerRepaint(); } catch (e) { finish(); }
  setTimeout(finish, 600);
})"""


def have_webkit():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.webkit.launch().close()
        return True
    except Exception:
        return False


HAVE = have_webkit()


def until(pg, js, secs):
    for _ in range(int(secs * 4)):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    return False


def _b64(raw):
    return base64.b64encode(raw).decode()


def patched_sw():
    """Real sw.js, with public tile hosts answered from stand-ins.

    Playwright WebKit does not intercept a fetch the service worker lets through, so once
    the worker controls the page those requests would hit OpenStreetMap and OpenFreeMap.
    OSM is a synthetic PNG (200, then 429). OpenFreeMap is the stand-in style and one
    vector tile. The MapLibre worker script is the copy in this checkout.
    """
    with open(os.path.join(R, 'sw.js'), encoding='utf-8') as fh:
        src = fh.read()
    with open(os.path.join(R, 'vendor', 'maplibre-gl-csp-worker.js'), 'rb') as fh:
        worker = fh.read()
    hook = (
        "self.__hm429=false;"
        "self.__hmBytes=function(s){return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0)});};"
        "self.__hmTile=function(){return Promise.resolve(new Response(self.__hmBytes('%s'),{status:self.__hm429?429:200,"
        "headers:{'content-type':'image/png','access-control-allow-origin':'*','cache-control':'no-store'}}));};"
        "self.__hmLocal=function(req){var p=req.url.split('?')[0];"
        "if(p.indexOf('/vendor/maplibre-gl-csp-worker.js')<0)return null;"
        "return Promise.resolve(new Response(self.__hmBytes('%s'),{status:200,headers:{'content-type':'application/javascript'}}));};"
        "self.addEventListener('message',function(e){if(e&&e.data==='hm-test-429'){self.__hm429=true;"
        "if(e.source)e.source.postMessage('hm-test-429-on');}});"
        "self.addEventListener('fetch',function(e){var u=e.request.url,p=u.split('?')[0];"
        "if(u.indexOf('tiles.openfreemap.org')<0)return;var body,type;"
        "if(p.indexOf('.pbf')>=0&&p.indexOf('/fonts/')<0){body=self.__hmBytes('%s');type='application/x-protobuf';"
        "e.waitUntil(self.clients.matchAll().then(function(cs){cs.forEach(function(c){c.postMessage({hmPbf:p})})}));}"
        "else if(p.indexOf('/fonts/')>=0){body=new Uint8Array();type='application/x-protobuf';}"
        "else if(p.indexOf('/styles/')>=0&&p.indexOf('sprite')<0){body=%s;type='application/json';}"
        "else if(/\\.json$/.test(p)){body='{}';type='application/json';}"
        "else if(/\\.png$/.test(p)){body=self.__hmBytes('%s');type='image/png';}"
        "else{body='';type='text/plain';}"
        "e.respondWith(Promise.resolve(new Response(body,{status:200,headers:{'content-type':type,'access-control-allow-origin':'*'}})));});"
    ) % (_b64(PNG), _b64(worker), _b64(PBF), json.dumps(STYLE), _b64(PNG))
    old = "return fetch(e.request).then(r=>{if(r.ok){c.put(e.request,r.clone()).then(()=>trim(c))}return r})"
    new = "return self.__hmTile().then(r=>{if(r.ok){c.put(e.request,r.clone()).then(()=>trim(c))}return r})"
    shell = "const net=fetch(e.request).then(put);"
    shell_new = "const net=(self.__hmLocal&&self.__hmLocal(e.request))||fetch(e.request).then(put);"
    if src.count(old) != 1 or src.count(shell) != 1:
        raise AssertionError('sw.js no longer matches the test patch')
    return (hook + src.replace(old, new, 1).replace(shell, shell_new, 1)).encode()


class Source(unittest.TestCase):
    def test_worker_url_is_absolute_and_the_cache_tag_matches(self):
        with open(os.path.join(R, 'tiles.js'), encoding='utf-8') as fh:
            tiles = fh.read()
        self.assertIn("new URL('/vendor/maplibre-gl-csp-worker.js', document.baseURI).href", tiles)
        self.assertNotIn("setWorkerUrl('vendor/", tiles)
        with open(os.path.join(R, 'tiles.js'), 'rb') as fh:
            tag = 'h' + hashlib.sha256(fh.read()).hexdigest()[:12]
        for rel in ('index.html', 'sw.js'):
            with open(os.path.join(R, rel), encoding='utf-8') as fh:
                self.assertIn('tiles.js?v=' + tag, fh.read(), rel)


@unittest.skipUnless(HAVE, 'needs playwright webkit')
class WebKitVector(unittest.TestCase):
    def _run(self, device, service_worker):
        from playwright.sync_api import sync_playwright
        phase = {'bad': False}
        seen = {'pbf': []}
        outside = []
        errs = []

        def local(route):
            url = route.request.url
            path = url.split(BASE, 1)[1].split('?')[0].split('#')[0] or '/'
            if service_worker and path == '/sw.js':
                return route.fulfill(status=200, body=patched_sw(), headers={
                    'content-type': 'application/javascript', 'cache-control': 'no-store'})
            f = os.path.join(R, path.lstrip('/'))
            f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
            if not os.path.isfile(f):
                return route.fulfill(status=404, body='')
            with open(f, 'rb') as fh:
                body = fh.read()
            route.fulfill(status=200, body=body, headers={
                'content-type': mimetypes.guess_type(f)[0] or 'application/octet-stream', 'cache-control': 'no-store'})

        def osm(route):
            code = 429 if phase['bad'] else 200
            route.fulfill(status=code, content_type='image/png', body=PNG, headers={
                'access-control-allow-origin': '*', 'cache-control': 'no-store', 'x-helpmap-tile': 'stub'})

        def ofm(route):
            url = route.request.url.split('?')[0]
            if '.pbf' in url and '/fonts/' not in url:
                seen['pbf'].append(url)
                return route.fulfill(status=200, content_type='application/x-protobuf', body=PBF, headers={
                    'access-control-allow-origin': '*', 'x-helpmap-tile': 'stub'})
            if '/fonts/' in url:
                return route.fulfill(status=200, content_type='application/x-protobuf', body=b'', headers={
                    'access-control-allow-origin': '*'})
            if '/styles/' in url and 'sprite' not in url:
                return route.fulfill(status=200, content_type='application/json', body=STYLE, headers={
                    'access-control-allow-origin': '*'})
            if url.endswith('.json'):
                return route.fulfill(status=200, content_type='application/json', body='{}', headers={
                    'access-control-allow-origin': '*'})
            if url.endswith('.png'):
                return route.fulfill(status=200, content_type='image/png', body=PNG, headers={
                    'access-control-allow-origin': '*'})
            return route.fulfill(status=404, body='', headers={'access-control-allow-origin': '*'})

        def block(route):
            # MapLibre turns a decoded sprite into a blob: URL. That is not a network request.
            if route.request.url.startswith('blob:'):
                return route.continue_()
            outside.append(route.request.url[:140])
            route.abort()

        with sync_playwright() as p:
            browser = p.webkit.launch()
            iphone = dict(p.devices[device])
            iphone.pop('default_browser_type', None)
            ctx = browser.new_context(**iphone, service_workers='allow' if service_worker else 'block',
                                      geolocation={'latitude': 53.4808, 'longitude': -2.2426}, permissions=['geolocation'])
            ctx.add_init_script(IOS_WORKER)
            ctx.route('**/*', block)
            ctx.route('**://tile.openstreetmap.org/**', osm)
            ctx.route('**://*.openfreemap.org/**', ofm)
            ctx.route(BASE + '/**', local)
            ctx.route(BASE + '/', local)
            pg = ctx.new_page()
            pg.on('pageerror', lambda e: errs.append(str(e)[:240]))
            pg.goto(BASE + '/?nocount&tiles=debug', wait_until='load')
            self.assertTrue(until(pg, "() => window.TILE_ACTIVE==='osm' && document.querySelectorAll('#map img.leaflet-tile-loaded').length>=4", 25),
                            pg.evaluate("() => ({a: window.TILE_ACTIVE, imgs: document.querySelectorAll('#map img.leaflet-tile-loaded').length})"))
            if service_worker:
                self.assertTrue(until(pg, "() => !!navigator.serviceWorker.controller", 25), 'service worker did not take control')
                acked = pg.evaluate("""() => new Promise(done => {
                  const t = setTimeout(() => done(false), 4000);
                  navigator.serviceWorker.addEventListener('message', function on(e) {
                    if (e.data === 'hm-test-429-on') { clearTimeout(t); navigator.serviceWorker.removeEventListener('message', on); done(true); }
                  });
                  navigator.serviceWorker.controller.postMessage('hm-test-429');
                })""")
                self.assertTrue(acked, 'patched service worker did not acknowledge 429 mode')
            phase['bad'] = True
            pg.locator('#me').tap(force=True)
            pg.wait_for_timeout(300)
            pg.locator('#xnear').tap(force=True)
            painted = None
            for _ in range(PAINT_S * 2):
                try:
                    painted = pg.evaluate(PAINT)
                except Exception as e:
                    painted = {'error': str(e)[:200]}
                if painted.get('water') and painted['water'] == painted.get('n') and (seen['pbf'] or painted.get('pbfs')):
                    break
                pg.wait_for_timeout(500)
            browser.close()
        self.assertEqual(outside, [], 'request left the stand-in routes')
        syntax = [e for e in errs if 'did not match the expected pattern' in e or 'SyntaxError' in e]
        self.assertEqual(syntax, [], syntax)
        self.assertTrue(painted and painted.get('water') == painted.get('n') and painted.get('n', 0) > 0, painted)
        pbfs = seen['pbf'] or (painted.get('pbfs') or [])
        self.assertGreaterEqual(len(pbfs), 1, painted)
        self.assertTrue(all(str(u).endswith('.pbf') and '/fonts/' not in str(u) for u in pbfs), pbfs)
        self.assertEqual(painted['active'], 'openfreemap', painted)
        self.assertEqual(painted['v'], 'ready', painted)
        fo = painted['fo'] or {}
        self.assertEqual((fo.get('from'), fo.get('to'), str(fo.get('reason'))), ('osm', 'openfreemap', '429'), fo)
        self.assertEqual(painted['worker'], WORKER, painted)

    def test_iphone_13_service_worker_off(self):
        self._run('iPhone 13', False)

    def test_iphone_13_service_worker_on(self):
        self._run('iPhone 13', True)

    def test_iphone_se_service_worker_off(self):
        self._run('iPhone SE', False)

    def test_iphone_se_service_worker_on(self):
        self._run('iPhone SE', True)


if __name__ == '__main__':
    unittest.main()
