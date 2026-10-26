"""'Does the result make sense?' check (Dean, 25 Oct 2026). Runs in CI (tests/test_sense_check.py) and in every refresh
workflow after the publish gate / refresh guard; a failure stops the run, so nothing is published.
For a fixed set of real searches on all three types it drives the real page (local copy of the built site) and checks:
  1. the search centres in the right area (within TOL_KM of the ONS county/unitary label point in counties.json);
  2. each list is exactly the nearest places from that centre, strictly nearest first, with Open today OFF and ON
     (ON = places closed today hidden, places with no listed times still shown);
  3. the search follows the selected type (that type's list is the one scrolled into view);
  4. the scroll after Search equals the scroll of the 'see list' button (v3scrollList).
Searches use the live postcodes.io API. If postcodes.io cannot be reached at all, the check reports SKIPPED (exit 0)
rather than blocking a refresh on someone else's outage. Results: reports/sense_check.md + logs/sense_check.json."""
import functools, http.server, json, math, os, sys, threading, urllib.request
import check_browser as B
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TOL_KM = 40
# query -> ONS CTYUA name the result must be near (counties.json)
SEARCHES = [('Littlehampton', 'West Sussex'), ('Suffolk', 'Suffolk'), ('Kent', 'Kent'), ('Devon', 'Devon'), ('West Sussex', 'West Sussex'),
            ('Fife', 'Fife'), ('Manchester', 'Manchester'), ('Cardiff', 'Cardiff'), ('Belfast', 'Belfast'),
            ('BN17 5LF', 'West Sussex'), ('M1 1AE', 'Manchester'), ('CF10 1EP', 'Cardiff'), ('EH1 1YZ', 'City of Edinburgh'), ('BT1 5GS', 'Belfast')]
TYPES = ('fb', 'ws', 'sh')
def hav(a, b, c, d):
    R = 6371; p = math.radians
    return 2 * R * math.asin(math.sqrt(math.sin(p(c - a) / 2) ** 2 + math.cos(p(a)) * math.cos(p(c)) * math.sin(p(d - b) / 2) ** 2))
def reachable():
    try: return urllib.request.urlopen('https://api.postcodes.io/postcodes/BN175LF', timeout=10).status == 200
    except Exception: return False
def settle(pg, first):
    """Wait, then until the scroll position has stopped moving (smooth scroll + late layout), max ~3 s."""
    pg.wait_for_timeout(first); last = None
    for _ in range(15):
        y = pg.evaluate('scrollY')
        if y == last: return
        last = y; pg.wait_for_timeout(200)
def run(base=None, chrome=None):
    from playwright.sync_api import sync_playwright
    cty = {a['name']: a for a in json.load(open(os.path.join(ROOT, 'counties.json')))['areas']}
    srv = None
    if not base:
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/?nocount' % srv.server_address[1]
    fails, rows = [], []
    with sync_playwright() as p:
        kw = {'executable_path': chrome} if chrome else {}
        b = p.chromium.launch(**kw)
        for w in (390, 1366):
            c = B.new_context(b, viewport={'width': w, 'height': 844}); pg = c.new_page()
            B.goto(pg, base); pg.wait_for_timeout(1500)
            for q, area in (SEARCHES if w == 390 else SEARCHES[:4]):  # desktop: a smaller set (same code path)
                for k in TYPES:
                    for on in (False, True):
                        if pg.evaluate("document.getElementById('openToday').checked") != on: pg.click('#v3open'); pg.wait_for_timeout(200)
                        pg.click('.v3b[data-l=%s]' % k); pg.wait_for_timeout(500)
                        pg.evaluate('()=>{scrollTo(0,0);lastNear=null}'); pg.fill('#q', q); pg.press('#q', 'Enter'); settle(pg, 2500)
                        r = pg.evaluate("""([k,on])=>{const D=k==='ws'?window.WARMSPACES:k==='sh'?window.SHELTERS:null;
                          const lat=lastNear?lastNear[0]:null,lng=lastNear?lastNear[1]:null;
                          const fbShown=[...document.querySelectorAll('#list .card')].map(c=>dists[+c.dataset.k]);
                          const fbAll=items.map((i,j)=>({i,j})).filter(x=>vis(x.j)&&!nc(x.i)).map(x=>dists[x.j]).sort((a,b)=>a-b);
                          let xs=[],xa=[];if(D){const nm=[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>h.textContent);
                            const pool=D.items.filter(i=>!i.ended&&(!on||!V3.shutToday(k,i))).map(i=>({n:i.name,d:hav(lat,lng,i.lat,i.lng)})).sort((a,b)=>a.d-b.d);
                            xa=pool.slice(0,nm.length).map(x=>x.n);  // names can repeat (e.g. 'The Meeting Place'): compare by name to the true nearest set
                            const used=new Set();xs=nm.map(n=>{const j=pool.findIndex((x,ix)=>x.n===n&&!used.has(ix));used.add(j);return j<0?-1:pool[j].d})}
                          return {lat,lng,fbShown,fbAll:fbAll.slice(0,fbShown.length),xs,xa,nm:D?[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>h.textContent):[],err:(document.querySelector('.v3err')||{}).textContent||''}}""", [k, on])
                        tag = '%s | %s | %s | open today %s | %dpx' % (q, k, area, 'on' if on else 'off', w); bad = []
                        if r['lat'] is None: bad.append('no result (%s)' % r['err'][:80])
                        else:
                            a = cty.get(area)
                            if a and hav(r['lat'], r['lng'], a['lat'], a['lng']) > TOL_KM: bad.append('centre %.0f km from %s' % (hav(r['lat'], r['lng'], a['lat'], a['lng']), area))
                            R6 = lambda xs: [round(x, 4) for x in xs]
                            if R6(r['fbShown']) != R6(sorted(r['fbShown'])): bad.append('food banks not nearest first')
                            if R6(r['fbShown']) != R6(r['fbAll']): bad.append('food banks are not the nearest set')
                            if k != 'fb':
                                if R6(r['xs']) != R6(sorted(r['xs'])): bad.append('%s not nearest first' % k)
                                if r['nm'] != r['xa']: bad.append('%s are not the nearest set' % k)
                            # follows the type + same scroll as the 'see list' button
                            s1 = pg.evaluate('scrollY'); pg.evaluate('()=>scrollTo(0,0)'); pg.evaluate("()=>v3scrollList(window.v3focus)"); settle(pg, 300)
                            s2 = pg.evaluate('scrollY'); foc = pg.evaluate('window.v3focus||"fb"')
                            if foc != k: bad.append('selected type lost (%s)' % foc)
                            if abs(s1 - s2) > 6: bad.append('scroll %d vs see-list %d' % (s1, s2))
                        rows.append(dict(search=tag, ok=not bad, problems=bad)); fails += [tag + ': ' + '; '.join(bad)] if bad else []
            c.close()
        b.close()
    if srv: srv.shutdown()
    return fails, rows
def report(fails, rows, note=''):
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    json.dump(dict(checks=len(rows), failed=len(fails), rows=rows, note=note), open(os.path.join(ROOT, 'logs', 'sense_check.json'), 'w'), indent=0)
    md = ['# Does the result make sense? (%d checks, %d failed)' % (len(rows), len(fails)), '', note] + ['- ' + f for f in fails] + ([] if fails else ['- all checks passed'])
    open(os.path.join(ROOT, 'reports', 'sense_check.md'), 'w').write('\n'.join(md) + '\n')
if __name__ == '__main__':
    if not reachable(): report([], [], 'SKIPPED: postcodes.io unreachable'); print('sense check SKIPPED: postcodes.io unreachable'); sys.exit(0)
    chrome = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None
    f, r = run(chrome=chrome); report(f, r)
    print('sense check: %d checks, %d failed' % (len(r), len(f))); [print(' FAIL', x) for x in f[:40]]
    sys.exit(1 if f else 0)
