"""Prove shelter filter chips on local checkout and live helpmap.uk (Dean).

Playwright 390×844, Shelter layer, Brighton / Manchester / London.
Records marker count, first 5 list types, Show more ×2; saves screenshots + JSON report.
Set HELPMAP_BASE=https://helpmap.uk for live; default is local static server.
"""
import functools, http.server, json, os, re, sys, threading, unittest
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ART = os.environ.get('CURSOR_ARTIFACTS_DIR', '/opt/cursor/artifacts')
CH = '/usr/bin/google-chrome'
try:
    import playwright  # noqa: F401
    HAVE_PW = os.path.exists(CH)
except Exception:
    HAVE_PW = False

CITIES = (
    ('Brighton', 'BN1 1EE'),
    ('Manchester', 'M1 1AE'),
    ('London', 'SW1A 1AA'),
)
CHIP_CASES = (
    ('hostel', {'shost': True}),
    ('day', {'sday': True}),
    ('youth', {'youth': True}),
    ('hostel+youth', {'shost': True, 'youth': True}),
    ('day+youth', {'sday': True, 'youth': True}),
)

AUDIT_JS = r"""
async (cfg) => {
  const { chips, city } = cfg;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const press = sel => {
    const e = document.querySelector(sel);
    if (!e || e.getAttribute('aria-pressed') === 'true') return;
    e.click();
  };
  for (const [k, on] of [['shost', chips.shost], ['youth', chips.youth], ['sday', chips.sday]]) {
    if (!on) continue;
    press('#chips [data-f=' + k + ']');
  }
  await sleep(400);
  const cs = [...document.querySelectorAll('#xlist > .card.xsh')];
  const fn = i => {
    if (!i || !window.shYouth) return '?';
    if (window.shYouth(i)) return 'youth';
    if (window.shDay(i)) return 'day';
    if (window.shHostel(i)) return 'hostel';
    return '?';
  };
  const okType = i => {
    if (!i) return false;
    const t = fn(i);
    if (chips.youth && chips.shost) return t === 'youth' || t === 'hostel';
    if (chips.youth && chips.sday) return t === 'youth' || t === 'day';
    if (chips.youth) return t === 'youth';
    if (chips.sday) return t === 'day';
    if (chips.shost) return t === 'hostel';
    return true;
  };
  const row = c => {
    const i = (window.SHELTERS && SHELTERS.items || []).find(x => x.id === c.dataset.id) || {};
    return { id: c.dataset.id, type: fn(i), name: (i.name || '').slice(0, 50), no_pin: !!i.no_pin };
  };
  let prev = -1;
  const nearestOk = cs.every(c => {
    if (!lastNear) return true;
    const i = SHELTERS.items.find(x => x.id === c.dataset.id) || {};
    const [a, b] = lastNear;
    const r = x => x * Math.PI / 180;
    const hv = (la, ln) => 12742 * Math.asin(Math.sqrt(
      Math.sin(r(la - a) / 2) ** 2 + Math.cos(r(a)) * Math.cos(r(la)) * Math.sin(r(ln - b) / 2) ** 2));
    const d = typeof i.lat === 'number' ? hv(i.lat, i.lng) : 1e9;
    const ok = d >= prev - 1e-6;
    prev = d;
    return ok;
  });
  const typesOk = cs.length > 0 && cs.every(c => okType(SHELTERS.items.find(x => x.id === c.dataset.id)));
  const pinIds = (window.__shVisiblePinIds || []).slice().sort();
  const rankPinIds = (window.__shRankPinIds || []).slice().sort();
  const pinsOk = JSON.stringify(pinIds) === JSON.stringify(rankPinIds);
  const before = cs.length;
  const btn = document.getElementById('xmore-sh');
  let more1 = 0, more2 = 0;
  if (btn && !btn.hidden) {
    btn.click();
    await sleep(350);
    more1 = document.querySelectorAll('#xlist > .card.xsh').length;
    if (!document.getElementById('xmore-sh').hidden) {
      document.getElementById('xmore-sh').click();
      await sleep(350);
      more2 = document.querySelectorAll('#xlist > .card.xsh').length;
    } else more2 = more1;
  } else more1 = more2 = before;
  const afterCs = [...document.querySelectorAll('#xlist > .card.xsh')];
  const moreTypesOk = afterCs.every(c => okType(SHELTERS.items.find(x => x.id === c.dataset.id)));
  const mapEmpty = pinIds.length === 0 && rankPinIds.some(id => {
    const i = SHELTERS.items.find(x => x.id === id);
    return i && !i.no_pin;
  });
  return {
    city,
    chips,
    markerCount: pinIds.length,
    rankPinCount: rankPinIds.length,
    listCount: afterCs.length,
    first5: afterCs.slice(0, 5).map(row),
    nearestOk,
    typesOk,
    pinsOk,
    moreTypesOk,
    mapEmpty,
    showMore: { before, after1: more1, after2: more2 },
    pass: typesOk && nearestOk && pinsOk && moreTypesOk && !mapEmpty,
  };
}
"""


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R)
    h.log_message = lambda *a: None
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, 'http://127.0.0.1:%d' % s.server_address[1]


def wait_page(pg, live=False):
    if live:
        for _ in range(120):
            try:
                ok = pg.evaluate("() => !!(document.getElementById('q') && window.map && document.querySelector('#map .leaflet-pane'))")
            except Exception:
                ok = False
            if ok:
                return
            pg.wait_for_timeout(500)
        raise AssertionError('live map not ready')
    from site_ready import wait_ready
    wait_ready(pg)


def run_matrix(base, label):
    from check_browser import stub_map_tiles
    live = base.startswith('http') and 'helpmap' in base

    os.makedirs(ART, exist_ok=True)
    rows = []
    pw = sync_playwright().start()
    b = pw.chromium.launch(executable_path=CH, headless=not live)
    kw = dict(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    if not live:
        kw['service_workers'] = 'block'
    ctx = b.new_context(**kw)
    if live:
        ctx.add_init_script("try{localStorage.setItem('v3layer','sh')}catch(e){}")
    if not live:
        stub_map_tiles(ctx)
        ctx.route(re.compile(r'https?://api\.postcodes\.io/.*'), lambda r: r.abort())
    pg = ctx.new_page()
    wait_until = 'load' if live else 'domcontentloaded'
    pg.goto(base + '/?nocount', wait_until=wait_until, timeout=120000)
    wait_page(pg, live=live)
    if not live:
        pg.evaluate("try{localStorage.setItem('v3layer','sh')}catch(e){}")
        pg.reload(wait_until=wait_until, timeout=120000)
        wait_page(pg, live=live)
    pg.evaluate("""() => {
      if (document.documentElement.dataset.v3k !== 'sh' && window.mark) mark('sh');
      const b = document.querySelector('.v3b[data-l=sh]');
      if (b && b.getAttribute('aria-checked') !== 'true') b.click();
    }""")
    pg.wait_for_timeout(800)
    pg.evaluate("""() => new Promise((ok, bad) => {
      if (window.SHELTERS && SHELTERS.items) return ok(true);
      const s = document.createElement('script'); s.src = 'shelters.js?t=' + Date.now();
      s.onload = () => ok(true); s.onerror = bad; document.body.appendChild(s);
    })""")
    pg.wait_for_timeout(500)

    for city, pc in CITIES:
        for name, chips in CHIP_CASES:
            pg.fill('#q', pc)
            pg.press('#q', 'Enter')
            pg.wait_for_timeout(900)
            for k in ('shost', 'youth', 'sday'):
                if pg.evaluate("k => document.querySelector('#chips [data-f='+k+']').getAttribute('aria-pressed')==='true'", k):
                    pg.evaluate("k => document.querySelector('#chips [data-f='+k+']').click()", k)
            for k, on in chips.items():
                if on and pg.evaluate("k => document.querySelector('#chips [data-f='+k+']').getAttribute('aria-pressed')!=='true'", k):
                    pg.evaluate("k => document.querySelector('#chips [data-f='+k+']').click()", k)
            pg.wait_for_timeout(500)
            res = pg.evaluate(AUDIT_JS, {'chips': chips, 'city': city})
            slug = re.sub(r'[^a-z0-9]+', '-', f'{label}-{city}-{name}').strip('-').lower()
            shot = os.path.join(ART, f'shelter-chip-{slug}.png')
            pg.locator('#map').screenshot(path=shot)
            res['screenshot'] = shot
            res['chip'] = name
            rows.append(res)

    ctx.close()
    b.close()
    pw.stop()
    report = {
        'at': datetime.now(timezone.utc).isoformat(),
        'base': base,
        'label': label,
        'rows': rows,
        'passed': sum(1 for r in rows if r.get('pass')),
        'total': len(rows),
    }
    path = os.path.join(ART, f'shelter-chip-report-{label}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    md = os.path.join(ART, f'shelter-chip-report-{label}.md')
    with open(md, 'w', encoding='utf-8') as f:
        f.write('| City | Chip | Markers | List | Pass | First 5 types |\n|---|---|---:|---:|:---:|---|\n')
        for r in rows:
            f.write('| %s | %s | %d | %d | %s | %s |\n' % (
                r['city'], r['chip'], r['markerCount'], r['listCount'],
                'PASS' if r.get('pass') else 'FAIL',
                ', '.join(x['type'] for x in r.get('first5', [])),
            ))
    return report


@unittest.skipUnless(HAVE_PW, 'needs chrome + playwright')
class LiveBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local_srv, cls.local_base = serve()

    @classmethod
    def tearDownClass(cls):
        cls.local_srv.shutdown()

    def test_local_preview_matrix(self):
        rep = run_matrix(self.local_base, 'local')
        self.assertEqual(rep['passed'], rep['total'], rep)

    def test_live_helpmap_matrix(self):
        base = os.environ.get('HELPMAP_BASE', 'https://helpmap.uk').rstrip('/')
        if 'skip_live' in os.environ:
            self.skipTest('HELPMAP skip_live')
        rep = run_matrix(base, 'live')
        self.assertEqual(rep['passed'], rep['total'], rep)


if __name__ == '__main__':
    label = sys.argv[1] if len(sys.argv) > 1 else 'live'
    base = os.environ.get('HELPMAP_BASE', 'https://helpmap.uk' if label == 'live' else None)
    if label == 'local':
        s, base = serve()
        try:
            print(json.dumps(run_matrix(base, 'local'), indent=2))
        finally:
            s.shutdown()
    else:
        print(json.dumps(run_matrix(base or 'https://helpmap.uk', label), indent=2))
