"""Dean rule 26: the map still works when the connection or the tile service is gone.

The browser is served from this checkout. Tile hosts are answered with a blank PNG here
and every other outside host is aborted, so the test never contacts helpmap.uk or a map server.
After the first online visit the browser is switched offline. The saved list, markers, opening
times and Call buttons must still work, and the offline line must name the date the copy was saved.
"""
import functools, http.server, os, re, struct, subprocess, threading, time, unittest, zlib
from urllib.parse import urlparse
R = os.path.join(os.path.dirname(__file__), '..')
CH = '/usr/bin/google-chrome'
try:
    import playwright
    HAVE = os.path.exists(CH)
except Exception:
    HAVE = False

READY = "() => !!(document.getElementById('q') && window.FB_DATA && FB_DATA.items && FB_DATA.items.length > 100 && document.querySelector('#map .leaflet-pane'))"
LINE = re.compile(r"^You\u2019re offline\. Showing places saved on \d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}, \d{2}:\d{2}\. Call before you go\.$")
TILE_HOSTS = ('tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com')

def blank_png():
    """1x1 light tile (#dddddd, the map's own background). Never fetched from a map server."""
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xdd\xdd\xdd')) + chunk(b'IEND', b''))

PNG = blank_png()

def tile_host(host):
    host = (host or '').lower()
    return host in TILE_HOSTS or host.endswith('.tile.openstreetmap.org')

# The search moves the map (fitBounds/flyTo), which drops the tiles of the previous view and loads the new ones from the
# worker's cache. Waiting only for "some tile loaded" could match the old view's tiles a moment before the move replaced
# them (CI run 40593928638: loaded 0). Wait until the move is over: no zoom animation, no tile still loading, and at
# least one painted tile, held for 300 ms.
TILES_SETTLED = r"""() => new Promise(ok => { const ready = () => { const m = document.getElementById('map');
  if (!m || m.querySelector('.leaflet-zoom-anim, .leaflet-tile-loading')) return false;
  return [...m.querySelectorAll('.leaflet-tile-loaded')].some(img => img.naturalWidth > 0) };
  if (!ready()) return ok(false); setTimeout(() => ok(ready()), 300) })"""
LIST = r"""() => {
  const cards = [...document.querySelectorAll('#list .card')];
  const hours = cards.map(c => (c.querySelector('.ot') || {}).innerText || '');
  const call = cards.map(c => c.querySelector('a.btn.call[href^="tel:"]')).find(Boolean);
  let clicked = false;
  if (call) call.addEventListener('click', e => { e.preventDefault(); clicked = true; }, true);
  if (call) call.click();
  const map = document.getElementById('map');
  const tile = document.querySelector('#map .leaflet-tile-pane');
  const loaded = [...document.querySelectorAll('#map .leaflet-tile-loaded')];
  return {
    cards: cards.length,
    text: cards.map(c => c.innerText).join('\n').slice(0, 500),
    hours: hours.filter(Boolean).slice(0, 4),
    href: call ? call.getAttribute('href') : '',
    callText: call ? call.innerText : '',
    clicked,
    markers: document.querySelectorAll('#map .leaflet-marker-icon').length,
    notiles: map.classList.contains('notiles'),
    bg: getComputedStyle(map).backgroundColor,
    filter: getComputedStyle(map).filter,
    tileFilter: tile ? getComputedStyle(tile).filter : '',
    tileOpacity: tile ? getComputedStyle(tile).opacity : '',
    loaded: loaded.length,
    wide: loaded.some(img => img.naturalWidth > 0),
    light: document.documentElement.classList.contains('light')
  };
}"""

LINE_JS = r"""() => {
  const e = document.getElementById('xoff');
  const raw = localStorage.getItem('savedAt');
  const dt = raw ? new Date(raw) : null;
  const p2 = n => String(n).padStart(2, '0');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const expect = dt && !isNaN(+dt) ? ('You\u2019re offline. Showing places saved on ' + dt.getDate() + ' ' + months[dt.getMonth()] + ' ' + dt.getFullYear() + ', ' + p2(dt.getHours()) + ':' + p2(dt.getMinutes()) + '. Call before you go.') : '';
  return {hidden: !e || e.hidden, text: e ? e.textContent : '', expect, onLine: navigator.onLine};
}"""


class Static(unittest.TestCase):
    def test_cache_is_bounded_and_old_caches_are_dropped(self):
        sw = open(os.path.join(R, 'sw.js'), encoding='utf-8').read()
        self.assertIn('TMAX=300', sw)
        self.assertIn('k.length-TMAX', sw)
        self.assertIn("k.filter(x=>x!==C&&x!==T).map(x=>caches.delete(x))", sw)
        self.assertIn("if(hit&&hit.type!=='opaque')return hit", sw)  # readable tiles stay cache-first; an opaque hit is refetched
        self.assertIn("'data.js'", sw)
        self.assertIn("'index.html'", sw)
        self.assertIn("'outcodes.json'", sw)
        self.assertIn("'counties.json'", sw)
        self.assertEqual(re.search(r"const C='([^']+)'", sw).group(1), 'fyfb-v93')

    def test_offline_line_and_plain_map_do_not_recolour_tiles(self):
        lj = open(os.path.join(R, 'layers.js'), encoding='utf-8').read()
        css = open(os.path.join(R, 'layers.css'), encoding='utf-8').read()
        tiles = open(os.path.join(R, 'tiles.js'), encoding='utf-8').read()
        html = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        self.assertIn("offline:'You\u2019re offline. Showing places saved on '", lj)
        self.assertIn("offEnd:'. Call before you go.'", lj)
        self.assertIn("chkL:'Listings last checked '", lj)  # existing wording check still has its string
        self.assertIn('#map.notiles .leaflet-tile-pane{opacity:0}', css)
        self.assertNotIn('invert(', css)
        self.assertNotRegex(css, r'leaflet-tile[^}{]*filter\s*:\s*(?!none)')
        self.assertIn('paintPlain', tiles)
        self.assertIn("name: 'maptiler', key: ''", tiles)
        self.assertIn('tile.openstreetmap.org', tiles)
        self.assertIn("if(!navigator.onLine)throw new Error('offline')", html)


def until(pg, js, secs=20):
    """Poll with evaluate. wait_for_function uses eval, which this site's CSP rejects."""
    last = None
    for _ in range(int(secs * 4)):
        try:
            last = pg.evaluate(js)
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, e)
        else:
            if last:
                return last
        pg.wait_for_timeout(250)
    raise AssertionError('timed out: %s last=%r' % (js[:160], last))


HOSTS = ('tile.openstreetmap.org', 'a.tile.openstreetmap.org', 'b.tile.openstreetmap.org', 'c.tile.openstreetmap.org',
         'api.maptiler.com', 'tiles.stadiamaps.com')
TILE_RULES = '--host-resolver-rules=' + ', '.join('MAP %s 127.0.0.1' % h for h in HOSTS)


def start_blank_tiles():
    """Blank PNG on 127.0.0.1:443 for every tile host. Chrome is pointed at this loopback address,
    so a tile fetch cannot reach a map server. The service worker fetches tiles itself (Playwright
    does not see that fetch), which is why the bytes are served here rather than only via route.fulfill."""
    d = '/tmp/hm-tiles'
    os.makedirs(d, exist_ok=True)
    cert, key, pidf = d + '/cert.pem', d + '/key.pem', d + '/pid'
    if not os.path.exists(cert):
        subprocess.check_call([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-keyout', key, '-out', cert, '-days', '1', '-nodes',
            '-subj', '/CN=tile.openstreetmap.org', '-addext',
            'subjectAltName=' + ','.join('DNS:' + h for h in HOSTS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = d + '/serve.py'
    open(script, 'w').write(
        'import http.server,os,ssl,struct,zlib\n'
        'def chunk(t,d):\n'
        ' return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)\n'
        'PNG=b"\\x89PNG\\r\\n\\x1a\\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"\\x00\\xdd\\xdd\\xdd"))+chunk(b"IEND",b"")\n'
        'class H(http.server.BaseHTTPRequestHandler):\n'
        ' def do_GET(self):\n'
        '  self.send_response(200);self.send_header("Content-Type","image/png");self.send_header("Access-Control-Allow-Origin","*");self.send_header("Content-Length",str(len(PNG)));self.end_headers();self.wfile.write(PNG)\n'
        ' def log_message(self,*a): pass\n'
        'class S(http.server.ThreadingHTTPServer):\n allow_reuse_address=True\n'
        's=S(("127.0.0.1",443),H)\n'
        'c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);c.load_cert_chain(%r,%r);s.socket=c.wrap_socket(s.socket,server_side=True)\n'
        'open(%r,"w").write(str(os.getpid()))\n'
        's.serve_forever()\n' % (cert, key, pidf))
    if os.path.exists(pidf):
        os.remove(pidf)
    proc = subprocess.Popen(['sudo', '-n', 'python3', script], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(50):
        if os.path.exists(pidf):
            return proc, pidf
        if proc.poll() is not None:
            err = proc.stderr.read().decode()[:300]
            raise RuntimeError('blank tile server did not start: ' + err)
        time.sleep(0.1)
    raise RuntimeError('blank tile server did not listen')


def stop_blank_tiles(proc, pidf):
    try:
        pid = open(pidf).read().strip()
        subprocess.call(['sudo', '-n', 'kill', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()


class Offline(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_offline_after_first_visit(self):
        from playwright.sync_api import sync_playwright
        tile_proc, tile_pid = start_blank_tiles()
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
        h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/?nocount' % srv.server_address[1]
        stray = []
        net = {'off': False}
        def handle(route):
            host = (urlparse(route.request.url).hostname or '').lower()
            if tile_host(host):
                # Page-level tile requests. The worker's own fetch is answered by the loopback tile server.
                if net['off']:
                    route.abort()
                    return
                route.fulfill(status=200, body=PNG, headers={
                    'content-type': 'image/png', 'access-control-allow-origin': '*', 'cache-control': 'public, max-age=300'})
                return
            if host in ('127.0.0.1', 'localhost'):
                if net['off']:
                    route.abort()
                    return
                route.continue_()
                return
            stray.append(route.request.url.split('?')[0][:120])
            route.abort()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH, args=['--ignore-certificate-errors', TILE_RULES])
                c = b.new_context(viewport={'width': 390, 'height': 844}, color_scheme='dark', service_workers='allow', ignore_https_errors=True)
                c.route('**/*', handle)
                pg = c.new_page()
                pg.goto(base, wait_until='domcontentloaded')
                until(pg, READY, 30)
                until(pg, "() => !!(navigator.serviceWorker && navigator.serviceWorker.controller)", 30)
                until(pg, "() => { try { return !!localStorage.getItem('savedAt') } catch (e) { return false } }", 10)
                # Second online load is controlled by the worker, so the shell and the tiles are actually cached.
                pg.reload(wait_until='domcontentloaded')
                until(pg, READY, 30)
                until(pg, "async () => { const cache = await caches.open('fyfb-tiles2'); return (await cache.keys()).length > 0 && document.querySelectorAll('#map .leaflet-tile-loaded').length > 0 }", 20)
                n0 = pg.evaluate("async () => (await (await caches.open('fyfb-tiles2')).keys()).length")
                pg.fill('#q', 'York')
                pg.press('#q', 'Enter')
                until(pg, "() => /YO\\d/.test(document.getElementById('list').innerText)", 20)
                until(pg, "async () => (await (await caches.open('fyfb-tiles2')).keys()).length > %d" % n0, 20)
                # Tile host is now refused, and the origin server is stopped. Anything still on screen came from the worker.
                # Drop the route first: aborting the navigation stops the worker from answering with its cache.
                net['off'] = True
                c.unroute('**/*', handle)
                stop_blank_tiles(tile_proc, tile_pid)
                tile_proc = None
                srv.shutdown()
                srv.server_close()
                c.set_offline(True)
                pg.reload(wait_until='domcontentloaded', timeout=20000)
                until(pg, READY, 30)
                until(pg, "() => { const e = document.getElementById('xoff'); return e && !e.hidden && /You\\u2019re offline/.test(e.textContent) }", 10)
                line = pg.evaluate(LINE_JS)
                self.assertFalse(line['hidden'], line)
                self.assertEqual(line['text'], line['expect'], line)
                self.assertRegex(line['text'], LINE)
                self.assertFalse(line['onLine'])
                until(pg, TILES_SETTLED, 15)
                cached = pg.evaluate(LIST)
                self.assertFalse(cached['notiles'], cached)
                self.assertGreater(cached['loaded'], 0, cached)
                self.assertTrue(cached['wide'], cached)
                # Town suggestions come from the page, then a postcode search uses the cached outcodes.
                pg.fill('#q', 'Yor')
                until(pg, "() => [...document.querySelectorAll('#ac li')].some(li => /York/.test(li.textContent))", 10)
                pg.fill('#q', 'York')
                pg.press('#q', 'Enter')
                until(pg, "() => /YO\\d/.test(document.getElementById('list').innerText) && document.querySelector('#list .ot')", 20)
                until(pg, TILES_SETTLED, 15)
                york = pg.evaluate(LIST)
                self._works(york, 'York')
                self.assertFalse(york['notiles'], york)
                self.assertTrue(york['wide'], york)
                self.assertGreater(york['loaded'], 0, york)
                pg.fill('#q', 'BN17 5LF')
                pg.press('#q', 'Enter')
                until(pg, "() => /BN\\d|Littlehampton/.test(document.getElementById('list').innerText)", 20)
                postcode = pg.evaluate(LIST)
                self._works(postcode, 'BN17 5LF')
                # Nothing cached: markers and the text list stay, on the plain light background.
                pg.evaluate("caches.delete('fyfb-tiles2')")
                pg.reload(wait_until='domcontentloaded')
                until(pg, READY, 30)
                until(pg, "() => document.getElementById('map').classList.contains('notiles')", 15)
                pg.fill('#q', 'York')
                pg.press('#q', 'Enter')
                until(pg, "() => /YO\\d/.test(document.getElementById('list').innerText)", 20)
                plain = pg.evaluate(LIST)
                self._works(plain, 'no tiles')
                self.assertTrue(plain['notiles'], plain)
                self.assertEqual(plain['tileOpacity'], '0', plain)
                self.assertEqual(plain['filter'], 'none', plain)
                self.assertEqual(plain['tileFilter'], 'none', plain)
                self.assertFalse(plain['light'], plain)
                bg = [int(n) for n in re.findall(r'\d+', plain['bg'])[:3]]
                self.assertGreaterEqual(min(bg), 180, plain)  # the map's light #ddd, including in dark mode
                again = pg.evaluate(LINE_JS)
                self.assertEqual(again['text'], line['text'])
                self.assertEqual([u for u in stray if 'postcodes.io' not in u], [])
                b.close()
        finally:
            if tile_proc is not None:
                stop_blank_tiles(tile_proc, tile_pid)
            try:
                srv.shutdown()
            except Exception:
                pass

    def _works(self, row, where):
        self.assertGreaterEqual(row['cards'], 1, (where, row))
        self.assertGreaterEqual(row['markers'], 1, (where, row))
        self.assertTrue(row['clicked'], (where, row))
        self.assertRegex(row['href'], r'^tel:\+?\d{6,}$', (where, row))
        self.assertRegex(row['callText'], r'\d', (where, row))
        self.assertTrue(any('Opening times' in h and re.search(r'Mon|Tue|Wed|Thu|Fri|Sat|Sun|\d{1,2}:\d{2}', h) for h in row['hours']), (where, row))
        self.assertEqual(row['filter'], 'none', (where, row))
        self.assertEqual(row['tileFilter'], 'none', (where, row))


if __name__ == '__main__':
    unittest.main()
