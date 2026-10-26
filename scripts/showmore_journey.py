"""Offline show-more journey (agent B). Drives a local copy of this checkout.

Contract the page must provide (showmore.js):
  window.SHOW_LIMITS = {first: 5, more: 10}
  window.showMoreResults()
  results rendered in #list as .card elements

What a search must do:
  - the first paint lists exactly SHOW_LIMITS.first cards (5), nearest first
  - the Show more button reveals exactly SHOW_LIMITS.more cards (15 total)
  - a later press reveals the rest (either the whole remainder, or further
    pages of `more`, the last page shorter), then the button hides
  - a new search goes back to 5 and the button returns
  - Use my location at Littlehampton (50.809, -0.540) puts
    "Littlehampton & District Foodbank" in those first 5
  - the same list works at phone widths, in dark mode, and in Welsh
    (the button reads "Dangos mwy")

Rule 25: this process serves the repo itself (python http.server) and never
opens https://helpmap.uk. Rule 23: every tile host is answered with a blank
PNG. A tile response that was not served by that stub fails the run.

Usage: python scripts/showmore_journey.py
Exit 1 when any check fails.
"""
import functools, http.server, os, sys, threading, time
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
CHROME_CANDIDATES = ('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/opt/google/chrome/google-chrome')
# Normal phone / desktop agents, same idea as scripts/check_browser.py, so the
# page's own beacon stays off and a headless UA never has to be answered.
PHONE_UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/129.0.6668.29 Mobile Safari/537.36 helpmap-check')
DESK_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/129.0.6668.29 Safari/537.36 helpmap-check')
READY = ("() => !!(document.getElementById('q') && window.FB_DATA && FB_DATA.items && "
         "FB_DATA.items.length > 100 && document.querySelector('#map .leaflet-pane'))")
# 1x1 transparent PNG. Tile images never leave the browser.
PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
       b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
       b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')
# Hosts named in the brief, matched on the hostname so a query string cannot hide one.
TILE_SUFFIXES = (
    'tile.openstreetmap.org',
    'openfreemap.org',
    'maptiler.com',
    'stadiamaps.com',
)
LITTLEHAMPTON = (50.809, -0.540)
FOODBANK = 'Littlehampton & District Foodbank'
HELPERS = r"""
window.__cards = function() {
  return [...document.querySelectorAll('#list .card')].filter(function(e) {
    if (e.closest('#sheet')) return false;
    var cs = getComputedStyle(e);
    return !e.hidden && cs.display !== 'none' && cs.visibility !== 'hidden' && e.offsetHeight > 0 && e.offsetWidth > 0;
  });
};
window.__cardNames = function() {
  return window.__cards().map(function(e) {
    var h = e.querySelector('h3');
    return h ? h.textContent.replace(/\s+/g, ' ').trim() : '';
  });
};
window.__cardMiles = function() {
  return window.__cards().map(function(e) {
    var d = e.querySelector('.d');
    var m = d && d.textContent.match(/[\d.]+/);
    return m ? parseFloat(m[0]) : null;
  });
};
window.__smb = function() {
  var re = /show more|dangos mwy/i;
  var all = document.querySelectorAll('button, [role="button"]');
  for (var i = 0; i < all.length; i++) {
    var e = all[i];
    if (e.closest('#sheet, #f')) continue;
    var text = (e.innerText || '').replace(/\s+/g, ' ').trim();
    var label = (e.getAttribute('aria-label') || '').trim();
    if (!re.test(text) && !re.test(label)) continue;
    var cs = getComputedStyle(e);
    if (e.hidden || e.getAttribute('aria-hidden') === 'true') continue;
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    if (!e.getClientRects().length || e.offsetHeight < 1) continue;
    return e;
  }
  return null;
};
window.__smbText = function() {
  var e = window.__smb();
  return e ? (e.innerText || '').replace(/\s+/g, ' ').trim() : '';
};
window.__eligible = function() {
  var items = (window.FB_DATA && FB_DATA.items) || [], n = 0, i, it;
  for (i = 0; i < items.length; i++) {
    it = items[i];
    if (!it || it.lat == null || it.lng == null) continue;
    if (it.kind === 'warehouse' || it.kind === 'dropoff') continue;
    n++;
  }
  return n;
};
"""


def chrome():
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def available():
    if not chrome():
        return False
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return True


def is_tile_url(url):
    """True when the request host is a map-tile host that must never be contacted."""
    host = (urlparse(url or '').hostname or '').lower().rstrip('.')
    if host.startswith('www.'):
        host = host[4:]
    return any(host == suffix or host.endswith('.' + suffix) for suffix in TILE_SUFFIXES)


def reveal_ok(before, after, total, more, step_index):
    """None when this reveal matches the contract, otherwise a short reason.

    The first press adds exactly `more` cards (or the short remainder when
    fewer than `more` exist). A later press adds another `more`, or finishes
    the list ("the rest", including a short last page).
    """
    gained = after - before
    if gained <= 0 or after > total:
        return 'count %s -> %s, total %s' % (before, after, total)
    if step_index == 0:
        expect = min(more, max(0, total - before))
        if gained != expect:
            return 'first Show more should add %s (got %s, now %s)' % (expect, gained, after)
        return None
    if after == total or gained == more:
        return None
    return 'expected +%s or the rest (got +%s, now %s of %s)' % (more, gained, after, total)


def button_ok(count, total, visible):
    """The button is on screen while cards remain, and gone once they are all shown."""
    if count < total:
        return None if visible else 'Show more hid with %s of %s cards shown' % (count, total)
    return None if not visible else 'Show more still visible after all %s cards' % total


def _lum(rgb):
    try:
        parts = rgb.replace('rgba(', '').replace('rgb(', '').rstrip(')').split(',')[:3]
        v = [int(float(x)) / 255 for x in parts]
    except Exception:
        return None
    v = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def _contrast(fg, bg):
    a, b = _lum(fg), _lum(bg)
    if a is None or b is None:
        return None
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


class Run(object):
    def __init__(self):
        self.rows = []
        self.net = {'stubbed': [], 'attempted': [], 'real': [], 'live': [], 'external': [], 'postcodes': 0}

    def add(self, name, ok, why=''):
        self.rows.append({'name': name, 'ok': bool(ok), 'why': '' if ok else (why or 'failed')})
        print((' PASS ' if ok else ' FAIL ') + name + ('' if ok or not why else ' — ' + why), flush=True)
        return ok


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return


def _serve():
    handler = functools.partial(_Quiet, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _route(context, net):
    def handle(route):
        url = route.request.url
        if is_tile_url(url):
            net['stubbed'].append(url)
            route.fulfill(status=200, body=PNG, content_type='image/png', headers={
                'x-showmore-stub': '1', 'access-control-allow-origin': '*', 'cache-control': 'no-store'})
            return
        low = url.lower()
        if 'helpmap.uk' in low:
            net['live'].append(url)
            route.abort()
            return
        if 'postcodes.io' in low:
            net['postcodes'] += 1
            # 503 makes the page use its built-in town list (offline), not the network.
            route.fulfill(status=503, content_type='application/json', body='{"status":503,"error":"offline"}')
            return
        host = (urlparse(url).hostname or '').lower()
        if host in ('127.0.0.1', 'localhost', '::1') or url.startswith(('data:', 'blob:')):
            route.continue_()
            return
        net['external'].append(url)
        route.abort()
    context.route('**/*', handle)


def _watch(page, net):
    def on_request(req):
        if is_tile_url(req.url):
            net['attempted'].append(req.url)
    def on_response(resp):
        if is_tile_url(resp.url) and resp.headers.get('x-showmore-stub') != '1':
            net['real'].append(resp.url)
    page.on('request', on_request)
    page.on('response', on_response)


def _context(browser, width, geo=False):
    kw = dict(
        viewport={'width': width, 'height': 844 if width < 800 else 900},
        color_scheme='dark',
        service_workers='block',
        user_agent=PHONE_UA if width < 800 else DESK_UA,
        locale='en-GB',
    )
    if width < 800:
        kw.update(has_touch=True, is_mobile=True)
    if geo:
        kw.update(geolocation={'latitude': LITTLEHAMPTON[0], 'longitude': LITTLEHAMPTON[1]}, permissions=['geolocation'])
    context = browser.new_context(**kw)
    context.set_default_timeout(60000)
    context.add_init_script(HELPERS)
    return context


def _until(page, expr, timeout=20):
    """Poll an expression. wait_for_function() evals in the page and the map's CSP blocks that."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = page.evaluate(expr)
        if last:
            return last
        page.wait_for_timeout(150)
    raise RuntimeError('timed out waiting for %s (last %r)' % (expr, last))


def open_ready(context, base):
    page = context.new_page()
    page.set_default_timeout(60000)
    page.set_default_navigation_timeout(20000)
    page.goto(base, wait_until='domcontentloaded', timeout=20000)
    _until(page, READY)
    return page


def _limits(page):
    return page.evaluate("""() => {
      const L = window.SHOW_LIMITS || {};
      return {first: L.first, more: L.more, fn: typeof window.showMoreResults};
    }""")


def _state(page):
    return page.evaluate("""() => ({
      n: window.__cards().length,
      names: window.__cardNames(),
      miles: window.__cardMiles(),
      btn: window.__smbText(),
      button: !!window.__smb(),
      total: window.__eligible(),
      lang: document.documentElement.lang || '',
      light: document.documentElement.classList.contains('light'),
      body: getComputedStyle(document.body).backgroundColor
    })""")


def _paint(page):
    """Colours of the Show more button, for the dark-mode check."""
    return page.evaluate("""() => {
      const e = window.__smb();
      if (!e) return null;
      const cs = getComputedStyle(e);
      let bg = cs.backgroundColor;
      if (!bg || bg === 'transparent' || /rgba\\(\\s*0\\s*,\\s*0\\s*,\\s*0\\s*,\\s*0\\s*\\)/.test(bg)) {
        let p = e.parentElement;
        while (p) { const g = getComputedStyle(p).backgroundColor;
          if (g && !/rgba\\(\\s*0\\s*,\\s*0\\s*,\\s*0\\s*,\\s*0\\s*\\)/.test(g) && g !== 'transparent') { bg = g; break; }
          p = p.parentElement; }
      }
      const box = e.getBoundingClientRect();
      return {color: cs.color, bg: bg, h: box.height, w: box.width, text: (e.innerText || '').replace(/\\s+/g, ' ').trim()};
    }""")


def _search(page, query):
    page.fill('#q', query)
    page.locator('button.go').click()
    _until(page, 'window.__cards().length >= 1')


def _click_more(page):
    handle = page.evaluate_handle('() => window.__smb()')
    el = handle.as_element()
    if el is None:
        raise RuntimeError('Show more button is not on the page')
    el.click()
    page.wait_for_timeout(50)


def _ordered(miles):
    if not miles or any(m is None for m in miles):
        return False
    return all(miles[i] + 0.2 >= miles[i - 1] for i in range(1, len(miles)))


def _finish_rest(page, limits):
    """Press Show more (via the contract function) until the list is complete."""
    return page.evaluate("""(more) => {
      const steps = [];
      let guard = 0;
      while (guard++ < 500) {
        const before = window.__cards().length;
        const total = window.__eligible();
        if (before >= total || !window.__smb()) break;
        window.showMoreResults();
        const after = window.__cards().length;
        steps.push(after - before);
        if (after <= before) break;
      }
      return {steps: steps, count: window.__cards().length, total: window.__eligible(), button: !!window.__smb()};
    }""", limits['more'])


def check_main(run, page):
    """English, dark, phone width: 5, then 10 more, then the rest, then a new search."""
    limits = _limits(page)
    contract = (limits.get('first') == 5 and limits.get('more') == 10 and limits.get('fn') == 'function')
    run.add('contract', contract, 'SHOW_LIMITS=%s showMoreResults=%s' % (limits, limits.get('fn')))
    if not contract:
        return
    _search(page, 'Littlehampton')
    st = _state(page)
    dark = (not st['light']) and (_lum(st['body']) or 1) < 0.25
    run.add('dark mode', dark, 'light class=%s body=%s' % (st['light'], st['body']))
    five = st['n'] == limits['first'] and _ordered(st['miles']) and FOODBANK in st['names'][:limits['first']]
    run.add('exactly 5 cards', five, 'cards=%s nearest=%s names=%s' % (st['n'], _ordered(st['miles']), st['names'][:6]))
    run.add('button says Show more', st['button'] and 'show more' in st['btn'].lower() and 'dangos mwy' not in st['btn'].lower(),
            'button=%r' % st['btn'])
    if st['n'] != limits['first'] or not st['button']:
        return
    first_names = st['names'][:limits['first']]
    _click_more(page)
    mid = _state(page)
    why = reveal_ok(st['n'], mid['n'], mid['total'], limits['more'], 0)
    kept = mid['names'][:limits['first']] == first_names and _ordered(mid['miles'])
    run.add('button reveals 10 more', why is None and kept and mid['n'] == limits['first'] + limits['more'],
            why or ('order kept=%s cards=%s' % (kept, mid['n'])))
    hidden = button_ok(mid['n'], mid['total'], mid['button'])
    if hidden:
        run.add('then the rest', False, hidden)
        return
    if mid['n'] < mid['total']:
        _click_more(page)
        nxt = _state(page)
        why2 = reveal_ok(mid['n'], nxt['n'], nxt['total'], limits['more'], 1)
        run.add('second press', why2 is None, why2 or ('cards=%s of %s' % (nxt['n'], nxt['total'])))
        if why2:
            run.add('then the rest', False, why2)
            run.add('button hides at the end', False, why2)
            return
        mid = nxt
    if mid['n'] < mid['total']:
        done = _finish_rest(page, limits)
        bad = None
        count = mid['n']
        for i, gained in enumerate(done['steps']):
            after = count + gained
            reason = reveal_ok(count, after, done['total'], limits['more'], i + 1)
            if reason:
                bad = reason
                break
            count = after
        if bad is None and (done['count'] != done['total'] or done['button']):
            bad = 'ended at %s of %s, button=%s, steps=%s' % (done['count'], done['total'], done['button'], len(done['steps']))
        run.add('then the rest', bad is None, bad or '')
        run.add('button hides at the end', bad is None and not done['button'], bad or '')
    else:
        end = _state(page)
        why_end = button_ok(end['n'], end['total'], end['button'])
        run.add('then the rest', end['n'] == end['total'] and why_end is None, why_end or ('cards=%s of %s' % (end['n'], end['total'])))
        run.add('button hides at the end', why_end is None, why_end or '')
    # A different town must start again at 5, with the button back.
    _search(page, 'York')
    again = _state(page)
    reset = (again['n'] == limits['first'] and again['button'] and 'show more' in again['btn'].lower()
             and again['names'][:1] != first_names[:1] and _ordered(again['miles']))
    run.add('new search resets to 5', reset, 'cards=%s button=%r first=%s' % (again['n'], again['btn'], again['names'][:1]))


def check_near(run, page):
    limits = _limits(page)
    if limits.get('fn') != 'function':
        run.add('near me Littlehampton', False, 'showMoreResults missing')
        return
    page.click('#me')
    _until(page, 'window.__cards().length >= 1')
    st = _state(page)
    ok = (st['n'] == 5 and FOODBANK in st['names'][:5] and _ordered(st['miles']) and st['button'])
    run.add('near me Littlehampton', ok, 'cards=%s names=%s button=%r msg=%s' % (
        st['n'], st['names'][:5], st['btn'], page.locator('#msg').inner_text()[:120]))
    if not ok:
        return
    _click_more(page)
    mid = _state(page)
    why = reveal_ok(5, mid['n'], mid['total'], limits.get('more') or 10, 0)
    run.add('near me show more', why is None and FOODBANK in mid['names'][:5], why or ('cards=%s' % mid['n']))


def check_welsh(run, page):
    limits = _limits(page)
    if limits.get('fn') != 'function':
        run.add('welsh', False, 'showMoreResults missing')
        return
    page.click('#xlang')
    _until(page, "document.documentElement.lang === 'cy'", timeout=10)
    _search(page, 'Littlehampton')
    st = _state(page)
    label = 'dangos mwy' in st['btn'].lower() and 'show more' not in st['btn'].lower()
    ok = st['lang'] == 'cy' and not st['light'] and st['n'] == 5 and label and FOODBANK in st['names'][:5]
    run.add('welsh', ok, 'lang=%s cards=%s button=%r light=%s' % (st['lang'], st['n'], st['btn'], st['light']))
    if not (st['n'] == 5 and st['button']):
        return
    paint = _paint(page)
    ratio = _contrast(paint['color'], paint['bg']) if paint else None
    run.add('welsh button readable', bool(paint) and paint['h'] >= 24 and paint['w'] >= 24 and (ratio or 0) >= 3,
            'paint=%s contrast=%s' % (paint, ratio))
    _click_more(page)
    mid = _state(page)
    why = reveal_ok(5, mid['n'], mid['total'], limits.get('more') or 10, 0)
    run.add('welsh show more', why is None and 'dangos mwy' in mid['btn'].lower(), why or ('cards=%s button=%r' % (mid['n'], mid['btn'])))


def check_narrow(run, page):
    limits = _limits(page)
    if limits.get('fn') != 'function':
        run.add('phone 360', False, 'showMoreResults missing')
        return
    _search(page, 'Littlehampton')
    st = _state(page)
    ok = st['n'] == 5 and st['button'] and not st['light'] and 'show more' in st['btn'].lower() and _ordered(st['miles'])
    run.add('phone 360', ok, 'cards=%s button=%r width=%s' % (st['n'], st['btn'], page.viewport_size['width']))
    if not ok:
        return
    paint = _paint(page)
    ratio = _contrast(paint['color'], paint['bg']) if paint else None
    run.add('phone button readable', bool(paint) and paint['h'] >= 24 and (ratio or 0) >= 3,
            'paint=%s contrast=%s' % (paint, ratio))
    _click_more(page)
    mid = _state(page)
    why = reveal_ok(5, mid['n'], mid['total'], limits.get('more') or 10, 0)
    run.add('phone 360 show more', why is None, why or ('cards=%s' % mid['n']))


def check_tiles(run):
    net = run.net
    missed = [u for u in net['attempted'] if u not in set(net['stubbed'])]
    real = list(net['real']) + missed
    run.add('no real tile request', not real and not net['live'],
            'unstubbed=%s live=%s stubbed=%d' % (real[:3], net['live'][:2], len(net['stubbed'])))
    run.add('stayed off the live site', not net['live'], ', '.join(net['live'][:3]))


def run():
    from playwright.sync_api import sync_playwright
    srv = _serve()
    base = 'http://127.0.0.1:%d/?nocount' % srv.server_address[1]
    out = Run()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome(), args=['--no-sandbox', '--disable-dev-shm-usage'])
            # 390px dark English: the full reveal, then a second search.
            ctx = _context(browser, 390)
            _route(ctx, out.net)
            try:
                page = open_ready(ctx, base)
                _watch(page, out.net)
                check_main(out, page)
            except Exception as e:
                out.add('five then the rest', False, str(e).splitlines()[0][:240])
            finally:
                ctx.close()
            # Near me, mocked to Littlehampton.
            ctx = _context(browser, 390, geo=True)
            _route(ctx, out.net)
            try:
                page = open_ready(ctx, base)
                _watch(page, out.net)
                check_near(out, page)
            except Exception as e:
                out.add('near me Littlehampton', False, str(e).splitlines()[0][:240])
            finally:
                ctx.close()
            # Welsh, still a phone, still dark.
            ctx = _context(browser, 390)
            _route(ctx, out.net)
            try:
                page = open_ready(ctx, base)
                _watch(page, out.net)
                check_welsh(out, page)
            except Exception as e:
                out.add('welsh', False, str(e).splitlines()[0][:240])
            finally:
                ctx.close()
            # A second phone width.
            ctx = _context(browser, 360)
            _route(ctx, out.net)
            try:
                page = open_ready(ctx, base)
                _watch(page, out.net)
                check_narrow(out, page)
            except Exception as e:
                out.add('phone 360', False, str(e).splitlines()[0][:240])
            finally:
                ctx.close()
            browser.close()
        check_tiles(out)
    finally:
        srv.shutdown()
    out.rows.append({'name': '_net', 'ok': True, 'why': 'stubbed %d tile, postcodes.io %d, other external %d' % (
        len(out.net['stubbed']), out.net['postcodes'], len(out.net['external']))})
    return out


def main():
    if not available():
        print('show-more journey needs google-chrome and playwright', flush=True)
        return 1
    out = run()
    failed = [r for r in out.rows if r['name'] != '_net' and not r['ok']]
    note = next((r['why'] for r in out.rows if r['name'] == '_net'), '')
    print('---')
    print('%d passed, %d failed. %s' % (sum(1 for r in out.rows if r['ok'] and r['name'] != '_net'), len(failed), note))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
