"""390px browser proof: food bank + warm space card type icons match markers/key (Dean)."""
import functools, http.server, json, os, re, sys, threading, unittest
from datetime import datetime, timezone

try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except ImportError:
    sync_playwright = None
    HAVE_PW = False

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ART = os.environ.get('CURSOR_ARTIFACTS_DIR', '/opt/cursor/artifacts')
CH = '/usr/bin/google-chrome'

AUDIT = r"""
async (layer) => {
  const card = document.querySelector(layer === 'fb' ? '#list > .card' : '#xlist > .card.xws');
  if (!card) return { ok: false, why: 'no card' };
  const box = card.querySelector('.xmkbox svg');
  const path = box && box.querySelector('path');
  const fill = path ? path.getAttribute('fill') : '';
  const d = path ? path.getAttribute('d') : '';
  const sym = card.querySelector('.xmkbox')?.dataset?.sym || '';
  const pill = card.querySelector('.xtop .utag');
  const pillBorder = pill ? getComputedStyle(pill).borderTopColor : '';
  const expect = layer === 'fb'
    ? { sym: 'food', fill: '#f5c518', shape: 'tear' }
    : { sym: 'flame', fill: '#d55e00', shape: 'dia' };
  const rgb = s => {
    const m = String(s).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  };
  const near = (a, b) => a && b && Math.abs(a[0]-b[0])<8 && Math.abs(a[1]-b[1])<8 && Math.abs(a[2]-b[2])<8;
  const expRgb = layer === 'fb' ? [245, 197, 24] : [213, 94, 0];
  const tear = d.includes('9.8 12.8') || d.startsWith('M16 5');
  const dia = d.includes('27.8') || (d.startsWith('M16 4') && d.includes('16 4'));
  const shapeOk = expect.shape === 'tear' ? tear : dia;
  return {
    layer,
    name: (card.querySelector('h3')||{}).textContent||'',
    sym,
    fill,
    shapeOk,
    pillBorder,
    pillOk: near(rgb(pillBorder), expRgb),
    symOk: sym === expect.sym && fill.toLowerCase() === expect.fill,
    pass: sym === expect.sym && fill.toLowerCase() === expect.fill && shapeOk && near(rgb(pillBorder), expRgb),
  };
}
"""


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, 'http://127.0.0.1:%d' % s.server_address[1]


def run_layer(base, layer, pc, label, live=False):
    from check_browser import stub_map_tiles
    import importlib.util
    _sr = importlib.util.spec_from_file_location('site_ready', os.path.join(os.path.dirname(__file__), 'site_ready.py'))
    wait_ready = importlib.util.module_from_spec(_sr)
    _sr.loader.exec_module(wait_ready)
    wait_ready = wait_ready.wait_ready
    os.makedirs(ART, exist_ok=True)
    launch = {'headless': not live}
    if os.path.exists(CH):
        launch['executable_path'] = CH
    pw = sync_playwright().start()
    b = pw.chromium.launch(**launch)
    ctx = b.new_context(
        viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
        service_workers='block' if not live else 'allow')
    if not live:
        stub_map_tiles(ctx)
    pg = ctx.new_page()
    if live:
        ctx.add_init_script("try{localStorage.setItem('v3layer','%s')}catch(e){}" % layer)
    pg.goto(base + '/?nocount', wait_until='load', timeout=120000)
    if not live:
        pg.evaluate("try{localStorage.setItem('v3layer',%s)}catch(e){}" % repr(layer))
        pg.reload(wait_until='load', timeout=120000)
    if live:
        for _ in range(120):
            if pg.evaluate('() => !!(window.map && document.getElementById("q"))'):
                break
            pg.wait_for_timeout(500)
    else:
        wait_ready(pg)
    if not live:
        pg.evaluate("""(layer) => { if (document.documentElement.dataset.v3k !== layer && window.mark) mark(layer); }""", layer)
    pg.evaluate("""(layer) => { const b = document.querySelector('.v3b[data-l='+layer+']'); if (b && b.getAttribute('aria-checked') !== 'true') b.click(); }""", layer)
    pg.wait_for_timeout(600)
    pg.fill('#q', pc)
    pg.press('#q', 'Enter')
    pg.wait_for_timeout(1200)
    sel = '#list > .card' if layer == 'fb' else '#xlist > .card.xws'
    pg.wait_for_selector(sel + ' .xtop', timeout=30000)
    res = pg.evaluate(AUDIT, layer)
    slug = re.sub(r'[^a-z0-9-]+', '-', '%s-%s-%s' % (label, layer, res.get('name', 'card'))).strip('-').lower()[:80]
    shot = os.path.join(ART, 'type-icon-%s.png' % slug)
    card = pg.locator(sel).first
    try:
        card.locator('.xtop').screenshot(path=shot, timeout=10000)
    except Exception:
        card.screenshot(path=shot, timeout=10000, force=True)
    res['screenshot'] = shot
    ctx.close()
    b.close()
    pw.stop()
    return res


@unittest.skipUnless(HAVE_PW, 'needs playwright')
class TypeIconBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_food_bank_card_icon_local(self):
        r = run_layer(self.base, 'fb', 'BN17 5LF', 'after-local', live=False)
        self.assertTrue(r.get('pass'), r)

    def test_warm_space_card_icon_local(self):
        r = run_layer(self.base, 'ws', 'M1 1AE', 'after-local', live=False)
        self.assertTrue(r.get('pass'), r)

    def test_live_food_and_warm_if_requested(self):
        if os.environ.get('CI') and not os.environ.get('HELPMAP_TYPE_ICON_LIVE'):
            self.skipTest('live type icon check')
        base = os.environ.get('HELPMAP_BASE', 'https://helpmap.uk').rstrip('/')
        fb = run_layer(base, 'fb', 'BN17 5LF', 'live', live=True)
        ws = run_layer(base, 'ws', 'M1 1AE', 'live', live=True)
        rep = {'at': datetime.now(timezone.utc).isoformat(), 'fb': fb, 'ws': ws}
        with open(os.path.join(ART, 'type-icon-report-live.json'), 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=2)
        self.assertTrue(fb.get('pass'), fb)
        self.assertTrue(ws.get('pass'), ws)


if __name__ == '__main__':
    unittest.main()
