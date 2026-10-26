"""Real-click user-journey suite (Dean, 25 Oct 2026 - must be flawless). Drives the page the way a visitor does,
headless Chromium, at 390px and 1366px, light and dark, on all three types. Runs:
  - before every merge (tests.yml, required check on any push/PR touching site html/css/js),
  - against the live site after each deploy (deploy-check.yml; on failure the deploy commit is reverted),
  - in the daily check.
Journeys (each counted pass/fail):
  J1 search options land on the list: Search button, Enter, postcode, county name, place pick from the suggestions,
     'Use my location' (mocked), 'Find nearest ...' button, and the 'see list' pill - the chosen type's list heading is
     at the top of the screen, no map in view, the list is that type, strictly nearest first.
  J2 type tiles switch the list to that type after a search.
  J3 Open today on/off: exact note wording, closed-today hidden when on, nearest first both ways.
  J4 filters: Walk-ins, Voucher, Open today only, List only (no map), Light mode (theme flips), ✕ collapse / reopen.
  J5 card buttons: Directions (maps link to the place), Share (share sheet or copy), Call (tel: link), Facebook button.
  J6 pin tap opens the pop-up card for that place.
  J7 phone: one-finger drag on the map shows the two-finger note.
Usage: journeys.py [base-url]   (default: serve this checkout locally). Exit 1 on any failure.
Results: reports/journeys.md, logs/journeys.json, screenshots of failures in logs/journeys/."""
import functools, http.server, json, os, sys, threading, time
import check_browser as B
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SHOTS = os.path.join(ROOT, 'logs', 'journeys')
NOTE = 'Showing places open today. If no times are listed, call before you go.'
LH = (50.8095, -0.5405)  # Littlehampton (BN17 5LF), the mocked 'my location'
TYPES = ('fb', 'ws', 'sh')
INIT = """window.__shared=[];try{navigator.share=async d=>{window.__shared.push(d)};}catch(e){}
try{navigator.clipboard.writeText=async t=>{window.__shared.push({text:t})};}catch(e){}
window.open=(u)=>{window.__opened=(window.__opened||[]).concat([u]);return null};"""

class R:
    def __init__(s): s.res = {}
    def ok(s, j, tag, cond, why=''):
        r = s.res.setdefault(j, {'pass': 0, 'fail': 0, 'failures': []})
        if cond: r['pass'] += 1
        else:
            msg = tag + (': ' + why if why else '')
            r['fail'] += 1; r['failures'].append(msg)
            print(' FAIL', j, '-', msg, flush=True)  # so a job timeout still leaves each journey's own result
        return cond

def at_top(pg, k):
    """Chosen type's list heading near the top, and no map in view (on desktop the map may sit in its side column next to the list)."""
    return pg.evaluate("""(k)=>{const vh=innerHeight;let h=null;
      if(k==='fb')h=document.querySelector('#list>.lh');
      else{const sos=document.getElementById('v3sos');const want=k==='sh'?/shelter|lloches/i:/warm|cynnes/i;
        h=(k==='sh'&&sos&&!sos.hidden&&sos.offsetParent)?sos:[...document.querySelectorAll('#xlist .lh')].find(e=>want.test(e.textContent))}
      if(!h)return {ok:false,why:'no list heading'};const t=h.getBoundingClientRect().top;
      const m=document.getElementById('map').getBoundingClientRect();const hr=h.getBoundingClientRect();const side=m.right<=hr.left+2||m.left>=hr.right-2;  // desktop: map in its own side column beside the list (existing layout) is allowed; never above/over the list
      const mapIn=m.height>0&&m.bottom>4&&m.top<vh-4&&getComputedStyle(document.getElementById('map')).display!=='none'&&!side;
      return {ok:t>=-2&&t<=vh*0.25&&!mapIn,why:'heading at '+Math.round(t)+'px of '+vh+(mapIn?', map in view':'')}}""", k)

def order_ok(pg, k):
    return pg.evaluate("""(k)=>{if(!lastNear)return {ok:false,why:'no search centre'};const [a,b]=lastNear;let d=[];
      if(k==='fb')d=[...document.querySelectorAll('#list .card')].map(c=>dists[+c.dataset.k]);
      else{const D=k==='ws'?window.WARMSPACES:window.SHELTERS;const pool=D.items.map(i=>({n:i.name,d:hav(a,b,i.lat,i.lng)})).sort((x,y)=>x.d-y.d);const used=new Set();
        d=[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>{const j=pool.findIndex((x,ix)=>x.n===h.textContent&&!used.has(ix));used.add(j);return j<0?1e9:pool[j].d})}
      const s=[...d].sort((x,y)=>x-y);return {ok:d.length>0&&JSON.stringify(d)===JSON.stringify(s),why:d.length+' cards '+JSON.stringify(d.map(x=>Math.round(x)))}}""", k)

SUITE_LIMIT = 14 * 60  # finish and print before the 15-minute job step is killed

def fresh(b, w, scheme, geo=False):
    kw = dict(viewport={'width': w, 'height': 844 if w < 800 else 900}, color_scheme=scheme)
    if w < 800: kw.update(has_touch=True, is_mobile=True)
    if geo: kw.update(geolocation={'latitude': LH[0], 'longitude': LH[1]}, permissions=['geolocation'])
    c = B.new_context(b, **kw)  # normal phone or desktop agent, shared time limits, service worker blocked
    c.add_init_script(INIT); return c

def load(c, base):
    """Open the map through the shared helper (domcontentloaded, then search, list and map pane)."""
    pg = B.open_page(c, base)
    pg.wait_for_timeout(1000)
    return pg

def scenario(r, journey, tag, body):
    """One page. A timeout or crash is this journey's failure; the suite carries on with the next page."""
    if time.time() > scenario.deadline:
        r.ok(journey, tag, False, 'suite time limit (14 min)'); return
    box = {'c': None, 'pg': None}
    try: body(box)
    except Exception as e:
        if box['pg'] is not None: shot(box['pg'], tag)
        r.ok(journey, tag, False, str(e).splitlines()[0][:240])
    finally:
        if box['c'] is not None:
            try: box['c'].close()
            except Exception: pass
scenario.deadline = 0

def settle(pg, first=1800):
    pg.wait_for_timeout(first); last = None
    for _ in range(15):
        y = pg.evaluate('scrollY')
        if y == last: return
        last = y; pg.wait_for_timeout(200)

def pick(pg, k):
    pg.click('.v3b[data-l=%s]' % k); pg.wait_for_timeout(600)

def shot(pg, name):
    os.makedirs(SHOTS, exist_ok=True); p = os.path.join(SHOTS, name.replace(' ', '_').replace('|', '').replace('/', '-')[:120] + '.png')
    try: pg.screenshot(path=p)
    except Exception: pass

def check_landing(r, pg, j, tag, k):
    a = at_top(pg, k); o = order_ok(pg, k); foc = pg.evaluate("window.v3focus||'fb'")
    good = r.ok(j, tag + ' list at top', a['ok'], a['why']) & r.ok(j, tag + ' nearest first', o['ok'], o['why']) & r.ok(j, tag + ' type kept', foc == k, foc)
    if not good: shot(pg, tag)

def run(base=None, chrome=None, quick=False):
    from playwright.sync_api import sync_playwright
    srv = None
    if not base:
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/' % srv.server_address[1]
    base = base.rstrip('/') + '/?nocount'
    global LAST
    r = R(); LAST = r; combos = [(390, 'light'), (390, 'dark'), (1366, 'light'), (1366, 'dark')]
    scenario.deadline = time.time() + SUITE_LIMIT
    with sync_playwright() as p:
        b = B.launch(p.chromium, **({'executable_path': chrome} if chrome else {}))
        for w, sc in combos:
            V = '%dpx %s' % (w, sc)
            print('journeys %s' % V, flush=True)
            # J1 search options
            for k in TYPES:
                for how, q in (('Search button', 'Littlehampton'), ('Enter', 'Littlehampton'), ('postcode', 'BN17 5LF'), ('county', 'Kent')):
                    tag = '%s | %s | %s %s' % (V, k, how, q)
                    def body(box, k=k, how=how, q=q, tag=tag):
                        box['c'] = fresh(b, w, sc); box['pg'] = pg = load(box['c'], base); pick(pg, k); pg.fill('#q', q)
                        if how == 'Search button': pg.click('button.go')
                        else: pg.press('#q', 'Enter')
                        settle(pg); check_landing(r, pg, 'J1 search lands on list', tag, k)
                        if how == 'county':  # J2: tiles switch the list after a search
                            for k2 in TYPES:
                                if k2 == k: continue
                                try:
                                    pick(pg, k2); pg.wait_for_timeout(900)
                                    o = order_ok(pg, k2); foc = pg.evaluate("window.v3focus||'fb'")
                                    r.ok('J2 type tiles', '%s | %s -> %s' % (V, k, k2), o['ok'] and foc == k2, o['why'] + ' focus ' + foc)
                                except Exception as e:
                                    r.ok('J2 type tiles', '%s | %s -> %s' % (V, k, k2), False, str(e).splitlines()[0][:240])
                    scenario(r, 'J1 search lands on list', tag, body)
                def body_sug(box, k=k):
                    box['c'] = fresh(b, w, sc); box['pg'] = pg = load(box['c'], base); pick(pg, k); pg.type('#q', 'Littleham', delay=60); pg.wait_for_timeout(1800)
                    opt = pg.locator('#ac [role=option], #ac li, #ac button').first
                    if r.ok('J1 search lands on list', '%s | %s | suggestion shown' % (V, k), opt.count() > 0 and opt.is_visible()):
                        opt.click(); settle(pg); check_landing(r, pg, 'J1 search lands on list', '%s | %s | suggestion pick' % (V, k), k)
                scenario(r, 'J1 search lands on list', '%s | %s | suggestion' % (V, k), body_sug)
                # use my location (mocked) and Find nearest button
                for how in ('#me', '#xnear'):
                    def body_loc(box, k=k, how=how):
                        box['c'] = fresh(b, w, sc, geo=True); box['pg'] = pg = load(box['c'], base); pick(pg, k)
                        if pg.locator(how).is_visible(): pg.click(how); settle(pg, 2500); check_landing(r, pg, 'J1 search lands on list', '%s | %s | %s (location mocked)' % (V, k, how), k)
                        else: r.ok('J1 search lands on list', '%s | %s | %s visible' % (V, k, how), False, 'not visible')
                        if how == '#me':  # see-list pill (after scrolling back up)
                            pg.evaluate('scrollTo(0,0)'); pg.wait_for_timeout(300); pl = pg.locator('a.v3pl')
                            if r.ok('J1 search lands on list', '%s | %s | see-list pill shown' % (V, k), pl.count() > 0 and pl.first.is_visible()):
                                pl.first.click(); settle(pg, 900); check_landing(r, pg, 'J1 search lands on list', '%s | %s | see-list pill' % (V, k), k)
                    scenario(r, 'J1 search lands on list', '%s | %s | %s' % (V, k, how), body_loc)
            def body_j3(box):
                box['c'] = fresh(b, w, sc); box['pg'] = pg = load(box['c'], base)
                for k in TYPES:
                    try:
                        pick(pg, k)
                        for on in (True, False):
                            if pg.evaluate("document.getElementById('openToday').checked") != on: pg.click('#v3open'); pg.wait_for_timeout(300)
                            pg.fill('#q', 'BN17 5LF'); pg.press('#q', 'Enter'); settle(pg)
                            notes = pg.evaluate("[...document.querySelectorAll('.tnote')].filter(e=>!e.hidden&&e.offsetParent).map(e=>e.textContent)")
                            r.ok('J3 Open today', '%s | %s | on=%s note' % (V, k, on), notes == ([NOTE] if on else []), str(notes))
                            o = order_ok(pg, k); r.ok('J3 Open today', '%s | %s | on=%s nearest first' % (V, k, on), o['ok'], o['why'])
                            if on:
                                bad = pg.evaluate("""(k)=>k==='fb'?[...document.querySelectorAll('#list .card')].filter(c=>closedToday(items[+c.dataset.k])).length:
                                  [...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>(k==='ws'?WARMSPACES:SHELTERS).items.find(i=>i.name===h.textContent)).filter(i=>i&&V3.shutToday(k,i)).length""", k)
                                r.ok('J3 Open today', '%s | %s | closed-today hidden' % (V, k), bad == 0, '%d closed shown' % bad)
                    except Exception as e:
                        r.ok('J3 Open today', '%s | %s' % (V, k), False, str(e).splitlines()[0][:240])
            scenario(r, 'J3 Open today', '%s | open today' % V, body_j3)
            def body_j4(box):
                box['c'] = fresh(b, w, sc)
                try: box['pg'] = pg = load(box['c'], base)
                except Exception as e:
                    why = str(e).splitlines()[0][:240]
                    r.ok('J4 filters', '%s | page load' % V, False, why)
                    r.ok('J5 card buttons', '%s | page load' % V, False, why)
                    return
                pg.fill('#q', 'BN17 5LF'); pg.press('#q', 'Enter'); settle(pg)
                try:
                    for f, want in (('walk', 'walkin'), ('vouch', 'voucher')):
                        pg.evaluate('scrollTo(0,0)'); pg.click('.fchip[data-f=%s]' % f); pg.wait_for_timeout(700)
                        pressed = pg.get_attribute('.fchip[data-f=%s]' % f, 'aria-pressed') == 'true'
                        okc = pg.evaluate("(w)=>[...document.querySelectorAll('#list .card')].every(c=>{const i=items[+c.dataset.k];return accOk(i)})", want)
                        r.ok('J4 filters', '%s | %s on' % (V, f), pressed and okc, 'pressed=%s cards ok=%s' % (pressed, okc))
                        pg.click('.fchip[data-f=%s]' % f); pg.wait_for_timeout(500)
                        r.ok('J4 filters', '%s | %s off' % (V, f), pg.get_attribute('.fchip[data-f=%s]' % f, 'aria-pressed') != 'true')
                    pg.click('#v3open'); pg.wait_for_timeout(400)
                    r.ok('J4 filters', '%s | Open today only on' % V, pg.evaluate("document.getElementById('openToday').checked"))
                    pg.click('#v3open'); pg.wait_for_timeout(400)
                    pg.click('#v3list'); pg.wait_for_timeout(500)
                    nomap = pg.evaluate("document.documentElement.classList.contains('nomap')&&document.getElementById('map').getBoundingClientRect().height<5")
                    r.ok('J4 filters', '%s | List only hides the map' % V, nomap)
                    pg.click('#v3list'); pg.wait_for_timeout(500)
                    r.ok('J4 filters', '%s | List only off shows the map' % V, pg.evaluate("document.getElementById('map').getBoundingClientRect().height>100"))
                    before = pg.evaluate("document.documentElement.classList.contains('light')"); pg.click('#v3light'); pg.wait_for_timeout(400)
                    after = pg.evaluate("document.documentElement.classList.contains('light')")
                    r.ok('J4 filters', '%s | Light mode flips theme' % V, before != after, '%s -> %s' % (before, after)); pg.click('#v3light'); pg.wait_for_timeout(300)
                    pg.evaluate('scrollTo(0,0)'); pg.click('#fhide'); pg.wait_for_timeout(500)
                    hid = pg.evaluate("!document.querySelector('.fchip[data-f=walk]').offsetParent||document.getElementById('fwrap').classList.contains('hidden')||document.getElementById('fwrap').hidden")
                    tab = pg.locator('#ftab'); r.ok('J4 filters', '%s | ✕ collapses filters' % V, hid and tab.is_visible())
                    if tab.is_visible(): tab.click(); pg.wait_for_timeout(500)
                    r.ok('J4 filters', '%s | filters reopen' % V, pg.locator('.fchip[data-f=walk]').is_visible())
                except Exception as e:
                    r.ok('J4 filters', '%s | filters' % V, False, str(e).splitlines()[0][:240])
                try:  # J5 card buttons (food bank card near BN17 5LF), same results
                    card = pg.locator('#list .card').first
                    d = card.locator('a.gm').first; href = d.get_attribute('href') or ''
                    r.ok('J5 card buttons', '%s | Directions link' % V, 'google.com/maps/dir' in href and 'destination=' in href, href[:80])
                    tel = card.locator('a.call[href^="tel:"]').first
                    r.ok('J5 card buttons', '%s | Call link' % V, tel.count() > 0 and len((tel.get_attribute('href') or '').replace('tel:', '')) >= 10)
                    card.locator('.v3share').first.click(); pg.wait_for_timeout(500)
                    sh = pg.evaluate('window.__shared'); r.ok('J5 card buttons', '%s | Share' % V, bool(sh), str(sh)[:100])
                except Exception as e:
                    r.ok('J5 card buttons', '%s | cards' % V, False, str(e).splitlines()[0][:240])
            scenario(r, 'J4 filters', '%s | filters' % V, body_j4)
            def body_j6(box):
                box['c'] = fresh(b, w, sc)
                try: box['pg'] = pg = load(box['c'], base)
                except Exception as e:
                    why = str(e).splitlines()[0][:240]
                    r.ok('J5 card buttons', '%s | Facebook page load' % V, False, why)
                    r.ok('J6 pin pop-up', '%s | page load' % V, False, why)
                    return
                try:
                    pc = pg.evaluate("(()=>{const i=items.find(i=>i.fb_page&&!i.tel&&i.postcode);return i?i.postcode:null})()")
                    if pc:
                        pg.fill('#q', pc); pg.press('#q', 'Enter'); settle(pg)
                        fb = pg.locator('#list a.xfbk').first
                        r.ok('J5 card buttons', '%s | Facebook button (%s)' % (V, pc), fb.count() > 0 and 'facebook.com' in (fb.get_attribute('href') or ''))
                except Exception as e:
                    r.ok('J5 card buttons', '%s | Facebook' % V, False, str(e).splitlines()[0][:240])
                try:
                    pg.fill('#q', 'BN17 5LF'); pg.press('#q', 'Enter'); settle(pg); pg.evaluate('scrollTo(0,0)'); pg.wait_for_timeout(300)
                    pg.evaluate("document.getElementById('map').scrollIntoView({block:'center'})"); pg.wait_for_timeout(500)
                    xy = pg.evaluate("""(()=>{const m=document.getElementById('map').getBoundingClientRect();const p=[...document.querySelectorAll('#map .leaflet-marker-icon.pin')]
                      .map(e=>e.getBoundingClientRect()).find(b=>b.width&&b.left>m.left+20&&b.right<m.right-20&&b.top>Math.max(m.top,0)+20&&b.bottom<Math.min(m.bottom,innerHeight)-20);
                      return p?[p.left+p.width/2,p.top+p.height/2]:null})()""")  # a pin inside the visible map, tapped where a visitor would
                    if r.ok('J6 pin pop-up', '%s | pin visible' % V, bool(xy)):
                        pg.mouse.click(xy[0], xy[1]); pg.wait_for_timeout(900)
                        # food bank pins open a map pop-up card (Leaflet); warm space / shelter pins open the bottom sheet
                        op = pg.evaluate("(()=>{const p=document.querySelector('#map .leaflet-popup-content');if(p&&p.textContent.trim().length>20)return 'popup';const s=document.getElementById('sheet');return (s&&!s.hidden&&s.getClientRects().length&&s.textContent.trim().length>20)?'sheet':''  /* sheet is position:fixed, so no offsetParent */})()")
                        r.ok('J6 pin pop-up', '%s | pop-up card opens' % V, bool(op))
                        if op == 'popup': pg.click('#map .leaflet-popup-close-button'); pg.wait_for_timeout(400); r.ok('J6 pin pop-up', '%s | pop-up closes' % V, pg.locator('#map .leaflet-popup').count() == 0)
                        if op == 'sheet': pg.click('#sheet .x'); pg.wait_for_timeout(400); r.ok('J6 pin pop-up', '%s | pop-up closes' % V, pg.evaluate("(()=>{const s=document.getElementById('sheet');return s.hidden||!s.getClientRects().length||getComputedStyle(s).visibility==='hidden'||s.getBoundingClientRect().top>=innerHeight-2})()"))
                except Exception as e:
                    r.ok('J6 pin pop-up', '%s | pin' % V, False, str(e).splitlines()[0][:240])
            scenario(r, 'J6 pin pop-up', '%s | pin' % V, body_j6)
            if w < 800:
                def body_j7(box):
                    box['c'] = fresh(b, w, sc); box['pg'] = pg = load(box['c'], base)
                    pg.evaluate("""()=>{const m=document.querySelector('#map');m.scrollIntoView();const r=m.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;
                      const t=new Touch({identifier:1,target:m,clientX:x,clientY:y});m.dispatchEvent(new TouchEvent('touchstart',{touches:[t],targetTouches:[t],bubbles:true,cancelable:true}));
                      const t2=new Touch({identifier:1,target:m,clientX:x,clientY:y-80});m.dispatchEvent(new TouchEvent('touchmove',{touches:[t2],targetTouches:[t2],bubbles:true,cancelable:true}))}""")
                    pg.wait_for_timeout(400)
                    vis = pg.evaluate("[...document.querySelectorAll('body *')].some(e=>e.children.length==0&&/two fingers/i.test(e.textContent)&&e.getClientRects().length&&getComputedStyle(e).visibility!='hidden'&&getComputedStyle(e).opacity!='0')")
                    r.ok('J7 two-finger note', '%s | shown on one-finger drag' % V, vis)
                scenario(r, 'J7 two-finger note', '%s | two fingers' % V, body_j7)
        b.close()
    if srv: srv.shutdown()
    return r.res

LAST = None

def report(res, base):
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    json.dump(dict(base=base, at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), journeys=res), open(os.path.join(ROOT, 'logs', 'journeys.json'), 'w'), indent=1, ensure_ascii=False)
    L = ['# User-journey suite (%s)' % (base or 'local checkout'), '', '| journey | pass | fail |', '|---|---|---|']
    L += ['| %s | %d | %d |' % (j, v['pass'], v['fail']) for j, v in sorted(res.items())]
    for j, v in sorted(res.items()):
        if v['failures']: L += ['', '## %s failures' % j, ''] + ['- ' + f for f in v['failures']]
    open(os.path.join(ROOT, 'reports', 'journeys.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return sum(v['fail'] for v in res.values())

if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else None
    chrome = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None
    try: res = run(base, chrome)
    except Exception as e:   # a crash is a failure with a report, not just a traceback
        res = LAST.res if LAST else {}
        res.setdefault('J0 suite ran to the end', {'pass': 0, 'fail': 0, 'failures': []})
        res['J0 suite ran to the end']['fail'] += 1; res['J0 suite ran to the end']['failures'].append('crash: %s' % str(e).splitlines()[0][:300])
    n = report(res, base)
    for j, v in sorted(res.items()): print('%-28s pass %4d  fail %d' % (j, v['pass'], v['fail']))
    for j, v in sorted(res.items()):
        for f in v['failures'][:15]: print(' FAIL', j, '-', f)
    sys.exit(1 if n else 0)
