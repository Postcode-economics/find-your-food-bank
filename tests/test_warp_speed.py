"""Batch 4 / Operation Warp Speed (27 Oct 2026): sw.js behaviour, run in node with fake caches/fetch.
1. An <img> (no-cors) OpenStreetMap tile is fetched in cors mode and stored, so a repeat visit is served from cache.
   The tiles.js probe and the <img> for the same tile, the second arriving before the first copy is stored, make one
   network request between them.
2. data.js with a ?v=h<hash> stamp is cache-first; a new stamp fetches fresh and drops the old stamped copy;
   offline, the last copy still answers. Unstamped data.js stays network-first.
3. fyfb-v95: the tile cache is keyed by the URL string. put(url, corsResponse) is found by match(url) for both a
   CORS probe and a no-cors <img>. match(e.request) is a different key and misses."""
import json, os, re, shutil, subprocess, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
HARNESS = r"""
const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');
const store=new Map();let net=[],offline=false,slowPut=0,matches=[];const H={};
// Real Cache: put(url) / match(url) share one key (new Request(url)). A page Request does not: a CORS probe and a
// no-cors <img> both miss an entry stored under the URL string, which is why match(e.request) re-downloaded tiles.
const slot=r=>{if(typeof r==='string')return 'U:'+r;if(r&&typeof r.mode==='string'&&r.mode)return 'R:'+r.mode+':'+(r.url||'');if(r&&r.url)return 'U:'+r.url;return 'U:'+String(r)};
const cache={match:async r=>{matches.push(typeof r==='string'?'S:'+r:'R');return store.get(slot(r))},put:async(r,v)=>{if(slowPut)await new Promise(x=>setTimeout(x,slowPut));store.set(slot(r),v)},keys:async()=>[...store.keys()].filter(k=>String(k).startsWith('U:')).map(k=>({url:k.slice(2)})),delete:async r=>store.delete(slot(r)),addAll:async()=>{}};
global.caches={open:async()=>cache,keys:async()=>[],match:async r=>store.get(slot(r)),delete:async()=>true};
global.self={addEventListener:(t,f)=>{H[t]=f},clients:{matchAll:async()=>[],claim:async()=>{}},skipWaiting:()=>{}};
global.location={origin:'https://helpmap.uk',href:'https://helpmap.uk/'};
global.Request=function(u,o){this.url=u;Object.assign(this,o||{})};
global.Response={error:()=>({error:true})};
global.fetch=async r=>{net.push([r.url||r,r.mode]);if(offline)throw new Error('off');const mode=r.mode||'cors',op=mode==='no-cors'&&!String(r.url||r).startsWith(location.origin);return {ok:!op,type:op?'opaque':'cors',body:'net:'+(r.url||r)+'#'+net.length,clone(){return this}}};
new Function(src)();
const start=(url,mode)=>{let p;H.fetch({request:{url,method:'GET',mode:mode||'no-cors',destination:String(url).includes('tile.')?'image':'script'},respondWith:x=>{p=x},waitUntil:()=>{}});return p||Promise.resolve('passthrough')};
const go=async(url,mode)=>await start(url,mode);
const tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{const o={};
 const t='https://tile.openstreetmap.org/6/31/20.png';
 await go(t,'no-cors');await tick();o.img_fetched_cors=net[0][1]==='cors';o.img_tile_stored=store.has('U:'+t);
 const n=net.length;const r=await go(t,'no-cors');o.repeat_from_cache=net.length===n&&!r.error;
 const a='https://helpmap.uk/data.js?v=haaaaaaaaaaaa',b='https://helpmap.uk/data.js?v=hbbbbbbbbbbbb';
 const r1=await go(a,'no-cors');const n2=net.length;const r2=await go(a,'no-cors');o.stamped_cache_first=net.length===n2&&r2.body===r1.body;
 const r3=await go(b,'no-cors');o.new_stamp_fetched=r3.body!==r1.body&&net.length===n2+1;o.old_stamp_dropped=!store.has('U:'+a);
 const n3=net.length;await go('https://helpmap.uk/data.js','no-cors');o.unstamped_network_first=net.length===n3+1;
 slowPut=50;const t2='https://tile.openstreetmap.org/7/63/41.png',n4=net.length;
 const pr=start(t2,'cors');await new Promise(x=>setTimeout(x,5));const im=start(t2,'no-cors');const [q1,q2]=await Promise.all([pr,im]);
 o.one_request_per_tile=net.filter(x=>x[0]===t2).length===1&&net.length===n4+1&&!q1.error&&!q2.error&&store.has('U:'+t2);slowPut=0;
 const t3='https://tile.openstreetmap.org/9/255/170.png';
 const corsResponse={ok:true,type:'cors',body:'stored-cors',clone(){return this}};
 await cache.put(t3,corsResponse);
 const probe={url:t3,method:'GET',mode:'cors',destination:''},imgReq={url:t3,method:'GET',mode:'no-cors',destination:'image'};
 o.direct_match_url_hits=!!(await cache.match(t3))&&(await cache.match(t3)).body==='stored-cors';
 o.direct_match_request_misses=!(await cache.match(probe))&&!(await cache.match(imgReq));
 const n6=net.length,gCors=await go(t3,'cors'),gImg=await go(t3,'no-cors');
 o.match_url_hits_cors_and_nocors=net.length===n6&&gCors.body==='stored-cors'&&gImg.body==='stored-cors'&&matches.filter(m=>m==='S:'+t3).length>=2;
 offline=true;const r4=await go('https://helpmap.uk/data.js?v=hcccccccccccc','no-cors');o.offline_last_copy=!!r4.body;
 console.log(JSON.stringify(o))})();
"""
class WarpSW(unittest.TestCase):
    def test_sw_behaviour(self):
        node = shutil.which('node')
        if not node: raise unittest.SkipTest('node not installed')
        out = subprocess.run([node, '-e', HARNESS, str(ROOT / 'sw.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(len(got), 12, got)
        for k, v in got.items(): self.assertTrue(v, k)
    def test_index_stamps_match_file_hashes(self):
        import seo_meta as SM
        h = (ROOT / 'index.html').read_text(encoding='utf-8')
        for f in ('data', 'stamp', 'access'):
            tags = re.findall(r'<script\b[^>]*\bsrc="%s\.js(?:\?v=[^"]*)?"[^>]*>' % f, h)
            self.assertEqual(tags, [t for t in tags if 'src="%s.js?v=%s"' % (f, SM.content_stamp(str(ROOT), f + '.js')) in t], f)
            self.assertEqual(len(tags), 1, (f, tags))
    def test_worker_registers_from_the_head(self):
        h = (ROOT / 'index.html').read_text(encoding='utf-8')
        sw = (ROOT / 'sw.js').read_text(encoding='utf-8')
        layers = (ROOT / 'layers.js').read_text(encoding='utf-8')
        self.assertLess(h.index("navigator.serviceWorker.register('sw.js?v="), h.index('</head>'))
        self.assertNotIn('serviceWorker.register', layers)
        self.assertIn("updateViaCache:'none'", h)
        self.assertIn('self.skipWaiting()', sw)
        self.assertIn('self.clients.claim()', sw)
        self.assertIn("e.data==='hm-claim'", sw)
        self.assertIn("postMessage('hm-claim')", h)
        self.assertIn("n='hmctrl=1'", h.replace(' ', ''))
        self.assertIn("/[?&]hmctrl=1(?:&|$)/", h)
        # The one-time reload is skipped when the flag is already on the query, and when a heal reload is in progress.
        self.assertIn("if(!/[?&]hmctrl=1(?:&|$)/.test(location.search))return;location.reload()", h.replace(' ', '').replace('\n', ''))


class PanBackTiles(unittest.TestCase):
    """A controlling worker caches OSM tiles. Panning away and back must paint the first tiles from that
    worker: fyfb-tiles2 holds them, and the tile server is not asked again (Cache-Control: no-store, so the
    browser HTTP cache cannot answer)."""
    def test_pan_back_tiles_come_from_the_service_worker(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest('needs playwright')
        import http.server, ssl, threading
        from urllib.parse import urlparse
        import test_osm_default as O
        if not O.HAVE:
            raise unittest.SkipTest('needs playwright chromium')
        counts = {}
        lock = threading.Lock()

        class Site(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=str(ROOT), **k)
            def log_message(self, fmt, *a):
                pass

        class Tiles(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *a):
                pass
            def do_GET(self):
                host = (self.headers.get('Host') or '').split(':')[0].lower()
                path = urlparse(self.path).path
                if host.endswith('openstreetmap.org'):
                    with lock:
                        counts[path] = counts.get(path, 0) + 1
                    body = O.BLANK
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Vary', 'Accept-Encoding')
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(204)
                self.send_header('Content-Length', '0')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

        certs = __import__('tempfile').mkdtemp()
        site = tiles = None
        try:
            subprocess.check_call(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', os.path.join(certs, 'key.pem'),
                                   '-out', os.path.join(certs, 'cert.pem'), '-days', '1', '-nodes', '-subj', '/CN=tile.openstreetmap.org'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ctx_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx_ssl.load_cert_chain(os.path.join(certs, 'cert.pem'), os.path.join(certs, 'key.pem'))
            tiles = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Tiles)
            tiles.socket = ctx_ssl.wrap_socket(tiles.socket, server_side=True)
            site = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Site)
            threading.Thread(target=tiles.serve_forever, daemon=True).start()
            threading.Thread(target=site.serve_forever, daemon=True).start()
            rules = ', '.join('MAP %s 127.0.0.1:%d' % (host, tiles.server_address[1]) for host in O.STUB_HOSTS)
            with sync_playwright() as p:
                browser = p.chromium.launch(args=['--host-rules=' + rules, '--ignore-certificate-errors'])
                ctx = browser.new_context(viewport={'width': 1280, 'height': 800}, service_workers='allow',
                                           user_agent='Mozilla/5.0 helpmap-check')
                page = ctx.new_page()
                navs = []
                page.on('framenavigated', lambda fr: navs.append(fr.url) if fr == page.main_frame else None)
                page.goto('http://127.0.0.1:%d/?nocount' % site.server_address[1], wait_until='domcontentloaded')
                self.assertTrue(O.until(page, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 30),
                                'service worker did not take control')
                n = len(navs)
                page.wait_for_timeout(800)
                if len(navs) != n:
                    self.assertTrue(O.until(page, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 30),
                                    'controller missing after the claim reload')
                    page.wait_for_timeout(400)
                self.assertTrue(O.until(page, """() => !!(window.FB_DATA && document.querySelector('#map .leaflet-pane'))
                    && [...document.querySelectorAll('#map .leaflet-tile-loaded')].filter(i => (i.getAttribute('data-tile')||'').includes('tile.openstreetmap.org') && i.naturalWidth > 0).length >= 4
                    && !document.querySelector('#map .leaflet-tile-loading')""", 30), 'map did not paint OSM tiles')
                # Tiles fetched after the worker controls. Pan away, then back: the return must be the cache.
                page.evaluate("() => { const c = map.getCenter(); window.__hmHome = {lat: c.lat, lng: c.lng, z: map.getZoom()}; map.setView([51.5, -0.12], 7, {animate: false}); }")
                self.assertTrue(O.until(page, """async () => {
                    if (document.querySelector('#map .leaflet-tile-loading') || window.TILE_ACTIVE !== 'osm') return false;
                    const box = document.querySelector('#map').getBoundingClientRect();
                    const shown = [...document.querySelectorAll('#map .leaflet-tile-loaded')].filter(i => {
                        const r = i.getBoundingClientRect();
                        return r.width > 0 && r.right > box.left && r.left < box.right && r.bottom > box.top && r.top < box.bottom && i.naturalWidth > 0
                            && (i.getAttribute('data-tile')||'').includes('/7/');
                    }).map(i => new URL(i.getAttribute('data-tile')).pathname);
                    if (shown.length < 4) return false;
                    const keys = (await (await caches.open('fyfb-tiles2')).keys()).map(r => r.url);
                    if (!shown.every(p => keys.some(u => u.endsWith(p)))) return false;
                    window.__hmTilePaths = shown;
                    return true;
                }""", 25), 'pan-away tiles were not stored in fyfb-tiles2')
                paths = page.evaluate("() => window.__hmTilePaths")
                self.assertGreaterEqual(len(paths), 4, paths)
                with lock:
                    before = {p: counts.get(p, 0) for p in paths}
                self.assertTrue(all(before[p] >= 1 for p in paths), before)
                page.evaluate("() => map.setView([53.5, -1.5], 6, {animate: false})")
                self.assertTrue(O.until(page, """() => {
                    const orig = window.__hmTilePaths || [];
                    const now = [...document.querySelectorAll('#map img.leaflet-tile')].map(i => i.getAttribute('data-tile')||'');
                    return orig.every(p => !now.some(u => u.endsWith(p))) && document.querySelectorAll('#map .leaflet-tile-loaded').length >= 4
                        && !document.querySelector('#map .leaflet-tile-loading');
                }""", 25), 'the away view did not leave the screen')
                page.evaluate("() => { performance.clearResourceTimings(); map.setView([51.5, -0.12], 7, {animate: false}); }")
                self.assertTrue(O.until(page, """() => {
                    const want = window.__hmTilePaths || [];
                    const imgs = [...document.querySelectorAll('#map img.leaflet-tile')];
                    return want.length >= 4 && want.every(p => imgs.some(i => (i.getAttribute('data-tile')||'').endsWith(p) && i.naturalWidth > 0))
                        && !document.querySelector('#map .leaflet-tile-loading');
                }""", 25), 'pan back did not repaint the away tiles')
                with lock:
                    after = {p: counts.get(p, 0) for p in paths}
                cached = page.evaluate("""async () => (await (await caches.open('fyfb-tiles2')).keys()).map(r => r.url)""")
                timing = page.evaluate("""() => {
                    const want = window.__hmTilePaths || [];
                    const es = performance.getEntriesByType('resource').filter(e => want.some(p => e.name.endsWith(p)));
                    return {n: es.length, sw: es.filter(e => e.workerStart > 0).length};
                }""")
                self.assertGreaterEqual(len(cached), 1, 'fyfb-tiles2 is empty')
                self.assertTrue(all(any(u.endswith(p) for u in cached) for p in paths), (paths[:4], cached[:8]))
                self.assertEqual(after, before, ('pan-back tiles were downloaded again', before, after))
                self.assertGreater(timing['n'], 0, timing)
                self.assertEqual(timing['sw'], timing['n'], timing)
                browser.close()
        finally:
            if site: site.shutdown()
            if tiles: tiles.shutdown()
            shutil.rmtree(certs, ignore_errors=True)


if __name__ == '__main__': unittest.main()
