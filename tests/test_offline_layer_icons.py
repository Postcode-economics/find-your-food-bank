"""Offline shell still serves unified layer icons (Dean 1 Nov 2026).

Hermetic: local site + service worker precache. Live: HELPMAP_OFFLINE_LIVE=1 on helpmap.uk after deploy."""
import json, os, sys, unittest
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ART = os.environ.get('CURSOR_ARTIFACTS_DIR', '/opt/cursor/artifacts')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_showmore_layers import until
from test_phone_qa_28oct import pc_stub

SYMBOL_JS = r"""() => {
  const bag = 'M9 13.5h14l-1.3 10.5H10.3z';
  const flame = 'M16.2 7.2c';
  const house = 'M8 15.5l8-7.5';
  const cardSym = (sel, needle) => {
    const svg = document.querySelector(sel);
    return svg && (svg.innerHTML || '').includes(needle);
  };
  const anyShCardIcon = () => [...document.querySelectorAll('#xlist .card.xsh .xmkbox svg')].some(svg => {
    const h = svg.innerHTML || '';
    return h.includes('M3 3h26v26H3z')
      && (h.includes('M8 15.5l8-7.5') || h.includes('M16 8v2.8') || (h.includes('>16<') && h.includes('>25<')));
  });
  const pinSym = (sel, needle) => {
    const el = document.querySelector(sel);
    const html = (el && el.innerHTML) || '';
    if (html.includes(needle)) return true;
    const ms = (window.LAYERS && LAYERS.sh && LAYERS.sh._ms) || [];
    const m = ms.find(x => x._keep && x._icon && x._icon.options && String(x._icon.options.html || '').includes(needle));
    return !!m;
  };
  return {
    offline: !navigator.onLine,
    map: !!document.querySelector('#map .leaflet-pane'),
    fbCard: cardSym('#list > .card .xmkbox svg', bag),
    fbPin: pinSym('.leaflet-marker-icon.pin svg', bag),
    shCard: anyShCardIcon(),
    shPin: pinSym('.leaflet-marker-icon.xpin svg', house),
    cards: document.querySelectorAll('#xlist .card.xsh').length,
    pass: !navigator.onLine
      && !!document.querySelector('#map .leaflet-pane')
      && anyShCardIcon()
      && document.querySelectorAll('#xlist .card.xsh').length > 0
      && (pinSym('.leaflet-marker-icon.xpin svg', house)
          || pinSym('.leaflet-marker-icon.xpin svg', 'M16 8v2.8')
          || anyShCardIcon()),
  };
}"""

LAYER_READY = "() => window.SHELTERS && document.querySelector('.v3b[data-l=sh][aria-checked=true]')"


def _have_pw():
    try:
        import playwright  # noqa
        return True
    except Exception:
        return False


@unittest.skipUnless(_have_pw(), 'needs playwright')
class OfflineLayerIcons(unittest.TestCase):
    def _run(self, base, live=False):
        import check_browser as CB
        from site_ready import wait_ready
        from playwright.sync_api import sync_playwright

        os.makedirs(ART, exist_ok=True)
        launch = {'headless': not live}
        if os.path.exists('/usr/bin/google-chrome'):
            launch['executable_path'] = '/usr/bin/google-chrome'
        pw = sync_playwright().start()
        b = pw.chromium.launch(**launch)
        ctx = b.new_context(
            viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
            service_workers='allow' if live else 'block')
        if not live:
            CB.stub_map_tiles(ctx)
        ctx.add_init_script("try{localStorage.setItem('v3layer','sh')}catch(e){}")
        ctx.route('https://api.postcodes.io/**', pc_stub)
        pg = ctx.new_page()
        pg.goto(base + '/?nocount', wait_until='load', timeout=120000)
        if not live:
            wait_ready(pg)
        assert until(pg, LAYER_READY, None, 60), 'shelter layer not ready'
        pg.fill('#q', 'M1 1AE')
        pg.press('#q', 'Enter')
        assert until(pg, "() => document.querySelectorAll('#xlist .card.xsh .xmkbox').length > 0", None, 60)
        if not live:
            for _ in range(40):
                if pg.evaluate('() => !!(window.LAYERS && LAYERS.sh && LAYERS.sh.on)'):
                    break
                pg.wait_for_timeout(500)
        ctx.set_offline(True)
        pg.reload(wait_until='domcontentloaded', timeout=120000)
        pg.wait_for_timeout(4000)
        res = pg.evaluate(SYMBOL_JS)
        shot = os.path.join(ART, 'offline-icons-%s.png' % ('live' if live else 'local'))
        try:
            pg.locator('#map').screenshot(path=shot, timeout=15000)
            pg.locator('#xlist .card.xsh').first.locator('.xtop').screenshot(
                path=shot.replace('.png', '-sh-card.png'), timeout=15000)
        except Exception:
            pass
        res['screenshot'] = shot
        ctx.close()
        b.close()
        pw.stop()
        return res

    def test_offline_shelter_icons_local_sw(self):
        import shutil, tempfile, http.server, threading
        import check_browser as CB
        from playwright.sync_api import sync_playwright
        from urllib.parse import urlparse

        tmp = tempfile.mkdtemp()
        site = os.path.join(tmp, 'site')
        shutil.copytree(ROOT, site, ignore=lambda d, names: [n for n in names if n in ('.git', 'logs', 'reports', 'tests', 'docs', 'export')])

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
        base = 'http://127.0.0.1:%d' % httpd.server_address[1]

        def route(r):
            host = urlparse(r.request.url).hostname or ''
            if host in ('127.0.0.1', 'localhost'):
                return r.continue_()
            if 'api.postcodes.io' in r.request.url:
                return pc_stub(r)
            if 'tile.openstreetmap.org' in r.request.url:
                return r.fulfill(status=200, body=CB.TILE_PNG, headers={'content-type': 'image/png', 'access-control-allow-origin': '*'})
            return r.abort()

        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path='/usr/bin/google-chrome') if os.path.exists('/usr/bin/google-chrome') else p.chromium.launch()
                ctx = CB.new_context(b, viewport={'width': 390, 'height': 844}, service_workers='allow')
                ctx.add_init_script("try{localStorage.setItem('v3layer','sh')}catch(e){}")
                ctx.route('**/*', route)
                pg = ctx.new_page()
                CB.goto(pg, base + '/?nocount', log=lambda *a: None)
                assert until(pg, LAYER_READY, None, 60), 'shelter layer not ready'
                pg.fill('#q', 'M1 1AE')
                pg.press('#q', 'Enter')
                assert until(pg, "() => document.querySelectorAll('#xlist .card.xsh .xmkbox').length > 0", None, 60)
                ctx.set_offline(True)
                pg.reload(wait_until='domcontentloaded', timeout=120000)
                pg.wait_for_timeout(5000)
                res = pg.evaluate(SYMBOL_JS)
                self.assertTrue(res.get('pass'), res)
                b.close()
        finally:
            httpd.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_live_offline_after_deploy(self):
        if not os.environ.get('HELPMAP_OFFLINE_LIVE'):
            self.skipTest('set HELPMAP_OFFLINE_LIVE=1 after deploy')
        base = os.environ.get('HELPMAP_BASE', 'https://helpmap.uk').rstrip('/')
        r = self._run(base, live=True)
        rep = {'at': datetime.now(timezone.utc).isoformat(), 'offline': r}
        with open(os.path.join(ART, 'offline-icons-live.json'), 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=2)
        self.assertTrue(r.get('pass'), r)


class ShellInventory(unittest.TestCase):
    def test_shell_lists_versioned_assets_and_icons(self):
        import hashlib
        import re
        import sw_version as sv

        lh = 'h' + hashlib.sha256(open(os.path.join(ROOT, 'layers.js'), 'rb').read()).hexdigest()[:12]
        sw = open(os.path.join(ROOT, 'sw.js'), encoding='utf-8').read()
        html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
        shell = re.findall(r"'([^']*)'", re.search(r"SHELL=\[([^\]]*)\]", sw).group(1))
        self.assertIn('icons.js', shell)
        self.assertIn('index.html', shell)
        self.assertIn('layers.js?v=' + lh, shell)
        self.assertEqual(sorted(x for x in shell if '?v=' in x), sv.wanted_versioned(html))
        self.assertIn("const C='fyfb-v97'", sw)


if __name__ == '__main__':
    unittest.main()
