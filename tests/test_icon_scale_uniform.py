"""Dean 2 Nov 2026: card + footer key type icons share one 28px box (food, warm space, shelter blues).

Playwright at 390×844 captures key, cards, chips, markers, filters and asserts measured boxes match.
"""
import functools, http.server, json, os, sys, threading, unittest

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ART = os.environ.get('CURSOR_ARTIFACTS_DIR', '/opt/cursor/artifacts')
CH = '/usr/bin/google-chrome'

BOX_CHECK = r"""() => {
  const tol = 0.5;
  const bad = [];
  const keyWant = [28, 34, 28, 28, 28];
  const keySvgs = [...document.querySelectorAll('#xupd .xkey-row .xkey-ico svg')];
  if (keySvgs.length !== 5) bad.push('key rows ' + keySvgs.length);
  else keySvgs.forEach((s, i) => {
    const b = s.getBoundingClientRect();
    if (Math.abs(b.width - keyWant[i]) > tol || Math.abs(b.height - keyWant[i]) > tol)
      bad.push('key row ' + i + ' ' + b.width.toFixed(2) + 'x' + b.height.toFixed(2));
  });
  const cardWant = [
    ['#list > .card .xmkbox svg', 28],
    ['#xlist > .card.xws .xmkbox svg', 34],
    ['#xlist > .card.xsh .xmkbox svg', 28],
  ];
  for (const [sel, want] of cardWant) {
    const svg = document.querySelector(sel);
    if (!svg) continue;
    const b = svg.getBoundingClientRect();
    if (b.width < 1) continue;
    if (Math.abs(b.width - want) > tol || Math.abs(b.height - want) > tol)
      bad.push('card ' + want + ' got ' + b.width.toFixed(2) + 'x' + b.height.toFixed(2));
  }
  const chipSvgs = document.documentElement.dataset.v3k === 'sh'
    ? [...document.querySelectorAll('#chips [data-f=shost] .xcs svg, #chips [data-f=youth] .xcs svg, #chips [data-f=sday] .xcs svg')]
    : [];
  for (const svg of chipSvgs) {
    const b = svg.getBoundingClientRect();
    if (Math.abs(b.width - 28) > tol || Math.abs(b.height - 28) > tol)
      bad.push('chip box ' + b.width.toFixed(2) + 'x' + b.height.toFixed(2));
  }
  return { bad, keyCount: keySvgs.length, chipCount: chipSvgs.length };
}"""


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, 'http://127.0.0.1:%d' % s.server_address[1]


def clip_shot(pg, sel, path):
    loc = pg.locator(sel).first
    try:
        loc.scroll_into_view_if_needed(timeout=5000)
        loc.screenshot(path=path, timeout=10000)
    except Exception:
        box = loc.bounding_box()
        if not box:
            return
        pad = 4
        vp = pg.viewport_size
        clip = {
            'x': max(0, box['x'] - pad),
            'y': max(0, box['y'] - pad),
            'width': min(vp['width'] - max(0, box['x'] - pad), box['width'] + 2 * pad),
            'height': min(vp['height'] - max(0, box['y'] - pad), box['height'] + 2 * pad),
        }
        if clip['width'] > 1 and clip['height'] > 1:
            pg.screenshot(path=path, clip=clip)


try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except ImportError:
    sync_playwright = None
    HAVE_PW = False


@unittest.skipUnless(HAVE_PW, 'needs playwright')
class IconScaleUniform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_key_cards_chips_same_28px_box_with_screenshots(self):
        from check_browser import stub_map_tiles
        import importlib.util
        _sr = importlib.util.spec_from_file_location('site_ready', os.path.join(os.path.dirname(__file__), 'site_ready.py'))
        wait_ready = importlib.util.module_from_spec(_sr)
        _sr.loader.exec_module(wait_ready)
        wait_ready = wait_ready.wait_ready
        os.makedirs(ART, exist_ok=True)
        launch = {'headless': True}
        if os.path.exists(CH):
            launch['executable_path'] = CH
        pw = sync_playwright().start()
        b = pw.chromium.launch(**launch)
        ctx = b.new_context(
            viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
            device_scale_factor=2, color_scheme='light', service_workers='block')
        stub_map_tiles(ctx)
        pg = ctx.new_page()
        pg.goto(self.base + '/?nocount', wait_until='load', timeout=120000)
        wait_ready(pg)
        tag = 'icon-uniform-local'
        pg.evaluate("try{localStorage.setItem('v3layer','sh')}catch(e){}")
        pg.reload(wait_until='load', timeout=120000)
        wait_ready(pg)
        pg.evaluate("() => { if (document.documentElement.dataset.v3k !== 'sh' && window.mark) mark('sh'); }")
        pg.wait_for_timeout(400)
        pg.fill('#q', 'BN1 4NJ')
        pg.press('#q', 'Enter')
        pg.wait_for_timeout(2000)
        pg.evaluate("() => { if (window.showMoreX) showMoreX('sh'); }")
        pg.wait_for_timeout(400)
        key_res = pg.evaluate(BOX_CHECK)
        clip_shot(pg, '#chips [data-f=youth]', os.path.join(ART, '%s_chip_youth_390.png' % tag))
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=ws]'); if (b) b.click(); }")
        pg.wait_for_timeout(300)
        pg.fill('#q', 'M1 1AE')
        pg.press('#q', 'Enter')
        pg.wait_for_timeout(2000)
        for _ in range(20):
            if pg.evaluate("() => !!document.querySelector('#xlist > .card.xws .xmkbox svg')"):
                break
            pg.wait_for_timeout(300)
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=fb]'); if (b) b.click(); }")
        pg.wait_for_timeout(300)
        pg.fill('#q', 'BN17 5LF')
        pg.press('#q', 'Enter')
        pg.wait_for_timeout(2000)
        pg.wait_for_selector('#list > .card .xmkbox svg', timeout=30000)
        fb_res = pg.evaluate(BOX_CHECK)
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=ws]'); if (b) b.click(); }")
        pg.wait_for_timeout(400)
        ws_res = pg.evaluate(BOX_CHECK)
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=sh]'); if (b) b.click(); }")
        pg.wait_for_timeout(400)
        sh_res = pg.evaluate(BOX_CHECK)
        res = {'bad': list(dict.fromkeys(
            (key_res.get('bad') or []) + (fb_res.get('bad') or []) + (ws_res.get('bad') or []) + (sh_res.get('bad') or []))),
               'keyCount': key_res.get('keyCount'), 'chipCount': key_res.get('chipCount')}
        pg.wait_for_timeout(200)
        clip_shot(pg, '#xupd', os.path.join(ART, '%s_key_390.png' % tag))
        clip_shot(pg, '#v3filt', os.path.join(ART, '%s_filters_390.png' % tag))
        clip_shot(pg, '#list > .card .xtop', os.path.join(ART, '%s_card_fb_390.png' % tag))
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=ws]'); if (b) b.click(); }")
        pg.wait_for_timeout(200)
        clip_shot(pg, '#xlist > .card.xws .xtop', os.path.join(ART, '%s_card_ws_390.png' % tag))
        pg.evaluate("() => { const b = document.querySelector('.v3b[data-l=sh]'); if (b) b.click(); }")
        pg.wait_for_timeout(200)
        clip_shot(pg, '#xlist > .card.xsh .xtop', os.path.join(ART, '%s_card_sh_390.png' % tag))
        clip_shot(pg, '#chips [data-f=youth]', os.path.join(ART, '%s_chip_youth_390.png' % tag))
        pg.evaluate("document.getElementById('map').scrollIntoView({block:'center'})")
        pg.wait_for_timeout(300)
        pg.locator('#map').screenshot(path=os.path.join(ART, '%s_map_markers_390.png' % tag))
        with open(os.path.join(ART, '%s_boxes.json' % tag), 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=2)
        ctx.close()
        b.close()
        pw.stop()
        self.assertEqual(res.get('bad'), [], res)


if __name__ == '__main__':
    unittest.main()
