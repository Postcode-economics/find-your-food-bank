"""Card design lock (Dean 25 Oct 13:40/13:39). Runs in CI (local checkout), after each deploy (live) and daily.
On list cards AND pin pop-up cards, all three types, 390 and 1366 px, light and dark, it checks:
  call button green, shows the number, tel: link = the number in the data; Directions yellow, Google Maps link;
  Share / text this address; Message on Facebook only where there is no phone, href = the verified Facebook page;
  Their website / Give Food / source links are http(s); Report a problem; type badge; status dot colour per state
  (red = closed, green = open, grey = unknown, colours locked below) and 'Times unknown' only when no times are parsed;
  every button/link tap target >= 44 px tall. Also counts call and Facebook buttons over every listing in the data.
  Type scale (Dean 31 Oct): on a phone (390px) and on desktop, the computed font-size and font-weight of the
  type badge, name, distance, address, info-row label and value, and phone digits, and the Directions / call /
  share button minimum heights, are the same on a food bank, a shelter and a warm space (list card and pin pop-up).
  Side-by-side buttons on one card share a height and the site font. The block from the first action button
  to the last holds buttons only (a phone caption sits on the Phone row).
Usage: python scripts/design_lock.py [BASE_URL] [--measure]. Report: reports/design_lock.md, logs/design_lock.json."""
import functools, http.server, json, os, sys, threading
from playwright.sync_api import sync_playwright
import check_browser as B
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
CHROME = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None
LOCK = json.load(open(os.path.join(ROOT, 'scripts', 'design_lock.json')))
PLACES = ['BN17 5LF', 'M1 1AE', 'CF10 1EP', 'SE1 7PB', 'EH1 1YZ']
CARDS_JS = r"""(sel)=>{const out=[];const rgb=e=>e?getComputedStyle(e).backgroundColor:null;
 for(const c of [...document.querySelectorAll(sel)].slice(0,8)){if(!c.offsetParent&&!c.getClientRects().length)continue;
  const q=s=>c.querySelector(s),all=s=>[...c.querySelectorAll(s)];const st=q('.v3st');
  const dot=st?getComputedStyle(st,'::before').backgroundColor:null;
  const call=all('a.btn.call').find(a=>(a.getAttribute('href')||'').startsWith('tel:'));
  const fb=all('a.xfbk,a[href*="facebook.com"].btn');const dir=q('a.btn.gm,a[href*="google.com/maps"]');
  const share=all('button,a').find(b=>/Share \/ text this address|Rhannu/.test(b.textContent));
  const rep=all('button,a').find(b=>/Report a problem/.test(b.textContent));
  const links=all('.links a,.src a,a.src').map(a=>a.getAttribute('href')||'');
  const small=all('a.btn,button.btn').filter(b=>b.offsetParent&&b.getBoundingClientRect().height<44).map(b=>b.textContent.trim().slice(0,30)+' '+Math.round(b.getBoundingClientRect().height)+'px');
  const timesShown=!!q('.ot .raw,.ot table,.ot li,.raw,table,.hrs,.xhours');
  out.push({name:(q('h3')||{}).textContent||'',k:c.dataset.k||'',status:st?st.className.replace('v3st','').trim():null,statusText:st?st.textContent.trim():'',dot,
   call:call?{href:call.getAttribute('href'),text:call.textContent.trim(),bg:rgb(call)}:null,
   fb:fb.map(a=>a.getAttribute('href')),dir:dir?{href:dir.getAttribute('href'),bg:rgb(dir)}:null,share:!!share,report:!!rep,
   badge:(q('.tag')||{}).textContent||'',links,small,timesShown})}
 return out}"""

# Same computed type on every layer. Missing pieces are skipped; a present piece that differs is a failure.
TYPE_JS = r"""(sel)=>{const cards=[...document.querySelectorAll(sel)].filter(c=>c.offsetParent||c.getClientRects().length);
 const c=cards[0];if(!c)return null;
 const pick=el=>{if(!el)return null;const s=getComputedStyle(el);return {fs:s.fontSize,fw:String(s.fontWeight),lh:s.lineHeight}};
 const row=c.querySelector('.ufact .xrow');const label=row&&row.querySelector('b');
 const stated=[...c.querySelectorAll('.ufact .xrow span,.xrow.uchk span')].find(s=>/Not stated|Heb ei nodi/.test(s.textContent||''));
 const call=[...c.querySelectorAll('a.btn.call')].find(a=>(a.getAttribute('href')||'').startsWith('tel:')&&!a.classList.contains('xfb'));
 const num=call&&(call.querySelector('.xnum')||call);
 const dir=c.querySelector('a.btn.gm,a[href*="google.com/maps"]');
 const share=[...c.querySelectorAll('button,a')].find(b=>/Share \/ text this address|Rhannu \/ tecstio/.test(b.textContent||''));
 const minH=el=>el?getComputedStyle(el).minHeight:null;
 const addr=[...c.children].find(e=>e.tagName==='P'&&!/xrow|sub|xday|xw|plab|warn/.test(e.className));
 return {badge:pick(c.querySelector('.tag,.utag,.xkind')),name:pick(c.querySelector('h3')),dist:pick(c.querySelector('.d')),
  addr:pick(addr),row:pick(row),label:pick((label&&label.querySelector('span'))||label),stated:pick(stated),phone:pick(num),
  call:call?{fs:pick(call).fs,fw:pick(call).fw,minH:minH(call)}:null,dir:dir?{fs:pick(dir).fs,fw:pick(dir).fw,minH:minH(dir)}:null,
  share:share?{fs:pick(share).fs,fw:pick(share).fw,minH:minH(share)}:null}}"""

# Side-by-side action buttons match in height and use the site font. Nothing but those buttons
# sits inside the vertical span from the first action button to the last (list card and pin pop-up).
BUTTON_JS = r"""(sel)=>{const bad=[];
 const cards=[...document.querySelectorAll(sel)].filter(c=>c.offsetParent||c.getClientRects().length).slice(0,8);
 const norm=s=>(s||'').replace(/["']/g,'').replace(/\s+/g,'').toLowerCase();
 const site=norm(getComputedStyle(document.body).fontFamily);
 const act=el=>el.matches&&el.matches('a.btn.gm,button.v3share,a.btn.web,a.btn.call')&&!el.classList.contains('xfb');
 for(const c of cards){
  const name=((c.querySelector('h3')||{}).textContent||'').trim().slice(0,40);
  const kids=[...c.children];
  const btns=kids.filter(act);
  if(!btns.length) continue;
  const rs=btns.map(b=>b.getBoundingClientRect());
  const y0=Math.min(...rs.map(r=>r.top)), y1=Math.max(...rs.map(r=>r.bottom));
  for(const el of kids){
   if(act(el)) continue;
   const r=el.getBoundingClientRect();
   if(r.width<2||r.height<2) continue;
   const mid=(r.top+r.bottom)/2;
   if(mid>y0+2 && mid<y1-2) bad.push(name+' loose '+(el.className||el.tagName)+' '+el.textContent.trim().slice(0,48));
  }
  const used=[];
  for(const b of btns){
   const r=b.getBoundingClientRect();
   let g=used.find(x=>x.top<r.bottom-4 && r.top<x.bottom-4);
   if(!g){g={top:r.top,bottom:r.bottom,items:[]};used.push(g)}
   g.top=Math.min(g.top,r.top); g.bottom=Math.max(g.bottom,r.bottom);
   const s=getComputedStyle(b);
   g.items.push({h:Math.round(r.height),ff:norm(s.fontFamily)});
  }
  for(const g of used){
   for(const i of g.items){ if(i.ff!==site) bad.push(name+' button font '+i.ff); }
   if(g.items.length<2) continue;
   const hs=g.items.map(i=>i.h);
   if(Math.max(...hs)-Math.min(...hs)>1) bad.push(name+' pair height '+hs.join(','));
   if(new Set(g.items.map(i=>i.ff)).size>1) bad.push(name+' pair font');
  }
 }
 return bad}"""

# Shelter symbols (Dean 31 Oct): the strip sits under the map only while Shelter is selected,
# its three symbols share one box, and it does not cover the OpenStreetMap credit.
STRIP_JS = r"""async ()=>{const bad=[];
 const shown=el=>!!(el&&el.getClientRects().length&&getComputedStyle(el).display!=='none');
 const sh=document.documentElement.dataset.v3k==='sh';
 const strip=document.getElementById('xsym');
 if(sh&&!shown(strip)) bad.push('symbol strip hidden while Shelter is selected');
 if(!sh&&shown(strip)) bad.push('symbol strip visible while Shelter is not selected');
 const youth=document.querySelector('#chips [data-f=youth]');
 const walk=document.querySelector('#chips [data-f=walk]');
 const vouch=document.querySelector('#chips [data-f=vouch]');
 const ink=svg=>new Promise(ok=>{const img=new Image();
  img.onload=()=>{const c=document.createElement('canvas');c.width=300;c.height=300;const x=c.getContext('2d');x.drawImage(img,0,0,300,300);
   const d=x.getImageData(0,0,300,300).data;let minx=300,miny=300,maxx=0,maxy=0,n=0;
   for(let y=40;y<260;y++)for(let xx=40;xx<260;xx++){const o=(y*300+xx)*4;if(d[o+3]<20||d[o]>=40||d[o+1]>=50||d[o+2]>=70)continue;n++;
    if(xx<minx)minx=xx;if(y<miny)miny=y;if(xx>maxx)maxx=xx;if(y>maxy)maxy=y;}
   ok(n?{w:maxx-minx+1,h:maxy-miny+1}:null);};
  img.onerror=()=>ok(null);img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(svg));});
 if(sh){
  if(!shown(youth)) bad.push('Young people chip hidden on shelters');
  if(shown(walk)||shown(vouch)) bad.push('food-bank chips still visible on shelters');
  const items=strip?[...strip.querySelectorAll('.xsy')]:[];
  if(items.length!==3) bad.push('strip symbols '+items.length);
  else {
   const tops=items.map(el=>el.getBoundingClientRect().top);
   if(Math.max(...tops)-Math.min(...tops)>2) bad.push('strip is not one line');
   const boxes=[]; for(const el of items) boxes.push(await ink(el.querySelector('svg')));
   if(boxes.some(b=>!b)) bad.push('symbol ink missing '+JSON.stringify(boxes));
   else boxes.forEach((b,i)=>{if(Math.abs(b.h-boxes[0].h)>4||Math.abs(b.w-boxes[0].w)>20) bad.push('symbol '+i+' ink '+b.w+'x'+b.h+' vs '+boxes[0].w+'x'+boxes[0].h);});
  }
  const attr=document.querySelector('#map .leaflet-control-attribution');
  if(attr&&strip){const a=attr.getBoundingClientRect(),s=strip.getBoundingClientRect();
   if(a.width&&s.width&&!(a.bottom<=s.top+1||s.bottom<=a.top+1||a.right<=s.left+1||s.right<=a.left+1)) bad.push('strip overlaps the map attribution');}
  const more=document.getElementById('xmore-sh');
  if(more&&shown(more)&&more.getBoundingClientRect().height<44) bad.push('Show more under 44px');
 } else if(shown(youth)) bad.push('Young people chip visible off the shelters layer');
 return bad}"""

# Type pill and symbol square (Dean): same height, tops and bottoms within 0.5px, 26px on a phone.
ALIGN_JS = r"""()=>{const bad=[];const rows=[...document.querySelectorAll('#xlist .card.xsh .xtop,#sheet.open .xtop')];
 const seen=new Set();
 if(!rows.length) return ['no shelter top row'];
 for(const row of rows){
  const pill=row.querySelector('.utag'); const svg=row.querySelector('.xmkbox svg');
  const sym=(row.querySelector('.xmkbox')||{}).dataset&&row.querySelector('.xmkbox').dataset.sym;
  seen.add(sym);
  const name=((row.closest('.card').querySelector('h3')||{}).textContent||'').trim().slice(0,32);
  if(!pill||!svg){bad.push(name+' missing symbol or pill'); continue}
  const kids=[...row.children];
  if(!kids[0]||!kids[0].classList.contains('xmkbox')||!kids[1]||!kids[1].classList.contains('utag')) bad.push(name+' order');
  const tr=pill.getBoundingClientRect(), sr=svg.getBoundingClientRect();
  if(Math.abs(sr.top-tr.top)>0.5||Math.abs(sr.bottom-tr.bottom)>0.5) bad.push(name+' align '+sr.top.toFixed(2)+' '+tr.top.toFixed(2)+' / '+sr.bottom.toFixed(2)+' '+tr.bottom.toFixed(2));
  if(Math.abs(sr.height-tr.height)>0.5) bad.push(name+' height '+sr.height.toFixed(2)+' vs '+tr.height.toFixed(2));
  if(Math.abs(sr.width-sr.height)>0.5) bad.push(name+' symbol not square');
  if(innerWidth<=430&&Math.abs(tr.height-26)>0.5) bad.push(name+' pill '+tr.height.toFixed(2)+'px');
 }
 for(const s of ['house','sun','youth']) if(!seen.has(s)) bad.push('missing '+s);
 return bad}"""

def type_diff(samples, where):
    """samples: layer -> metric dict. Fail when two layers both measured a piece and it is not the same."""
    bad, layers = [], [k for k, v in samples.items() if v]
    for i, a in enumerate(layers):
        for b in layers[i+1:]:
            for key in ('badge', 'name', 'dist', 'addr', 'row', 'label', 'stated', 'phone', 'call', 'dir', 'share'):
                x, y = samples[a].get(key), samples[b].get(key)
                if not x or not y: continue
                if x != y: bad.append('%s %s: %s %s vs %s %s' % (where, key, a, x, b, y))
    return bad

ENFORCE_TIMES = True   # Dean 31 Oct: a card that shows times must not say 'Times unknown' (partial weeks say Next open; text-only says Check times below)
KNOWN = []
TILES = []              # reported in reports/design_lock.md, do not fail the run

def check(cards, mode, where, k='fb'):
    for c in cards: c['k_type'] = k
    bad = []
    for c in cards:
        n = '%s [%s]' % (c['name'][:40], where)
        if c['k_type'] == 'fb' and not c['badge'].strip(): bad.append(n + ': no type badge')
        if not c['dir'] or 'google.com/maps' not in (c['dir']['href'] or ''): bad.append(n + ': Directions link')
        elif c['dir']['bg'] != LOCK['directions'][mode]: bad.append(n + ': Directions colour %s' % c['dir']['bg'])
        if not c['share']: bad.append(n + ': no Share / text this address')
        if not c['report']: bad.append(n + ': no Report a problem')
        if c['call']:
            digits = ''.join(ch for ch in c['call']['href'] if ch.isdigit())
            if not digits or digits not in ''.join(ch for ch in c['call']['text'] if ch.isdigit()): bad.append(n + ': call button number %r vs %r' % (c['call']['text'], c['call']['href']))
            if c['call']['bg'] != LOCK['call'][mode]: bad.append(n + ': call colour %s' % c['call']['bg'])
            if c['fb']: bad.append(n + ': Facebook button shown although there is a phone')
        for f in c['fb']:
            if not f.startswith('https://www.facebook.com/'): bad.append(n + ': Facebook href %s' % f)
        for h in c['links']:
            if not h.startswith(('http://', 'https://', 'faq.html', '/')): bad.append(n + ': link %s' % h)
        if c['status'] in LOCK['dot'][mode] and c['dot'] != LOCK['dot'][mode][c['status']]: bad.append(n + ': %s dot %s' % (c['status'], c['dot']))
        if c['timesShown'] and 'Times unknown' in c['statusText']:
            # Dean 31 Oct: times on the card and 'Times unknown' on the badge is a failure.
            (bad if ENFORCE_TIMES else KNOWN).append(n + ': times listed but status says Times unknown')
        bad += [n + ': tap target ' + s for s in c['small']]
    return bad

VIS_JS = """s=>{const m=document.getElementById('map').getBoundingClientRect();const p=[...document.querySelectorAll(s)]
  .map(e=>e.getBoundingClientRect()).find(b=>b.width&&b.left>m.left+20&&b.right<m.right-20&&b.top>Math.max(m.top,0)+20&&b.bottom<Math.min(m.bottom,innerHeight)-20);return p?[p.left+p.width/2,p.top+p.height/2]:null}"""

def data_counts(pg):
    return pg.evaluate("""(()=>{const fb=items;const tel=i=>typeof telOf==='function'?telOf(i):(i.phone||i.tel);
      const r={foodbanks:fb.length,fb_call:fb.filter(i=>tel(i)).length,fb_facebook:fb.filter(i=>!tel(i)&&i.fb_page).length};
      for(const [k,v] of [['ws','WARMSPACES'],['sh','SHELTERS']]){const d=(window[v]&&window[v].items)||((typeof LAYERS!=='undefined'&&LAYERS[k].data)||{}).items||[];r[k]=d.length;r[k+'_call']=d.filter(i=>i.phone).length}
      return r})()""")

def run(base=None, measure=False):
    srv = None
    if not base:
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
    base = base.rstrip('/'); bad, seen, counts, meas = [], 0, None, {}
    # Rule 23: map tiles are stubbed (new_context). No real tile is ever requested here.
    probe = {'status': 'not requested (rule 23)', 'url': '', 'ok': True, 'detail': ''}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
        for w in (390, 1366):
            for mode in ('light', 'dark'):
                kw = dict(viewport={'width': w, 'height': 900}, color_scheme=mode)
                if w < 800: kw.update(has_touch=True, is_mobile=True)
                c = B.new_context(b, **kw); pg = c.new_page()
                tiles = {'ok': 0, 'bad': 0}
                def _t(r, tiles=tiles):
                    if B.is_map_tile(r.url):
                        ok = r.status == 200 and 'image' in (r.headers.get('content-type') or '')
                        tiles['ok' if ok else 'bad'] += 1
                pg.on('response', _t)
                before = len(bad)
                try:
                    B.goto(pg, base + '/?nocount')
                    pg.wait_for_timeout(1000)
                except Exception as e:
                    bad.append('%dpx %s: page did not open: %s' % (w, mode, str(e).splitlines()[0][:200]))
                    print('FAIL design-lock %dpx %s (page)' % (w, mode), flush=True)
                    c.close(); continue
                pg.evaluate("m=>{document.documentElement.classList.toggle('light',m==='light');try{localStorage.setItem('theme',m)}catch(e){}}", mode)
                typed, typed_pop = {}, {}
                try:
                  for k, sel in (('fb', '#list .card'), ('ws', '#xlist .card.xws'), ('sh', '#xlist .card.xsh')):
                    pg.evaluate("k=>{const t=document.querySelector('#v3big [data-l='+k+']');if(t)t.click()}", k); pg.wait_for_timeout(500)
                    for q in PLACES:
                        pg.fill('#q', q); pg.press('#q', 'Enter'); pg.wait_for_timeout(2500)
                        cards = pg.evaluate(CARDS_JS, sel); seen += len(cards)
                        for x in cards:
                            if x['status']: meas.setdefault(mode, {}).setdefault(x['status'], set()).add(x['dot'])
                            if x['call']: meas.setdefault(mode, {}).setdefault('call', set()).add(x['call']['bg'])
                            if x['dir']: meas.setdefault(mode, {}).setdefault('dir', set()).add(x['dir']['bg'])
                        if not measure: bad += check(cards, mode, '%dpx %s %s %s list' % (w, mode, k, q), k)
                        if q == PLACES[0] and not typed.get(k):
                            typed[k] = pg.evaluate(TYPE_JS, sel)
                            if not measure:
                                bad += ['%dpx %s %s list %s' % (w, mode, k, x) for x in (pg.evaluate(BUTTON_JS, sel) or [])]
                                bad += ['%dpx %s %s' % (w, mode, x) for x in (pg.evaluate(STRIP_JS) or [])]
                                if k == 'sh' and w == 390:
                                    pg.fill('#q', 'BN1 4NJ'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2000)
                                    for _ in range(8):
                                        if pg.evaluate("()=>[...document.querySelectorAll('#xlist .xmkbox')].some(b=>b.dataset.sym==='youth')"):
                                            break
                                        pg.evaluate("()=>{if(window.showMoreX)showMoreX('sh')}")
                                        pg.wait_for_timeout(200)
                                    for lang in ('en', 'cy'):
                                        if lang == 'cy':
                                            pg.click('#xlang'); pg.wait_for_timeout(700)
                                        bad += ['%dpx %s %s %s' % (w, mode, lang, x) for x in (pg.evaluate(ALIGN_JS) or [])]
                                    if pg.evaluate("()=>document.documentElement.lang")=='cy':
                                        pg.click('#xlang'); pg.wait_for_timeout(400)
                                if k == 'sh':
                                    pg.click('#chips [data-f=youth]'); pg.wait_for_timeout(400)
                                    fy = pg.evaluate("""()=>{const ids=[...document.querySelectorAll('#xlist > .card.xsh')].map(c=>c.dataset.id);
                                      const bad=ids.filter(id=>{const i=(window.SHELTERS&&SHELTERS.items||[]).find(x=>x.id===id);return !i||i.kind!=='young_people'});
                                      return {n:ids.length, bad}}""")
                                    if not fy or fy.get('n') < 1 or fy.get('bad'): bad.append('%dpx %s youth filter %s' % (w, mode, fy))
                                    pg.click('#chips [data-f=youth]'); pg.wait_for_timeout(300)
                    # pin pop-up card (a place with pins of every type nearby)
                    pg.fill('#q', 'M1 1AE'); pg.press('#q', 'Enter'); pg.wait_for_timeout(2500)
                    pg.evaluate("document.getElementById('map').scrollIntoView({block:'center'})"); pg.wait_for_timeout(500)
                    psel = '#map .leaflet-marker-icon.pin' if k == 'fb' else '#map .leaflet-marker-icon.xpin'
                    xy = None
                    for _ in range(6):   # a pin may be inside a cluster: click a cluster to zoom in, then retry
                        xy = pg.evaluate(VIS_JS, psel)
                        if xy: break
                        cl = pg.evaluate(VIS_JS, '#map .leaflet-marker-icon.marker-cluster,#map .leaflet-marker-icon.xcl')
                        if cl: pg.mouse.click(*cl)
                        else: pg.evaluate("try{map.zoomOut()}catch(e){}")   # nearest pins can be off-screen: zoom out
                        pg.wait_for_timeout(900)
                    if not xy:
                        bad.append('%dpx %s %s pin pop-up: no tappable pin found' % (w, mode, k)); continue
                    pg.mouse.click(*xy); pg.wait_for_timeout(900)
                    pc = pg.evaluate(CARDS_JS, '#map .leaflet-popup-content .pop,#sheet.open #sheetBody .card')
                    if not pc: bad.append('%dpx %s %s pin pop-up: pin tapped, no pop-up card' % (w, mode, k))
                    elif not measure: bad += check(pc, mode, '%dpx %s %s pin pop-up' % (w, mode, k), k)
                    typed_pop[k] = pg.evaluate(TYPE_JS, '#map .leaflet-popup-content .pop,#sheet.open #sheetBody .card')
                    if not measure: bad += ['%dpx %s %s pop %s' % (w, mode, k, x) for x in (pg.evaluate(BUTTON_JS, '#map .leaflet-popup-content .pop,#sheet.open #sheetBody .card') or [])]
                    pg.keyboard.press('Escape'); pg.wait_for_timeout(300)
                  if not measure:
                    bad += type_diff(typed, '%dpx %s list type' % (w, mode))
                    bad += type_diff(typed_pop, '%dpx %s pop type' % (w, mode))
                except Exception as e:
                    bad.append('%dpx %s: %s' % (w, mode, str(e).splitlines()[0][:200]))
                TILES.append((w, mode, tiles['ok'], tiles['bad']))
                if base.startswith('https://'):   # live: the map must actually load tiles. A local run reports the count and still passes if the tile host is unreachable.
                    if not tiles['ok'] or tiles['bad'] > tiles['ok'] // 10: bad.append('%dpx %s map tiles: %d ok, %d failed' % (w, mode, tiles['ok'], tiles['bad']))
                added = len(bad) - before
                print(('PASS' if added == 0 else 'FAIL'), 'design-lock %dpx %s' % (w, mode), '' if added == 0 else '(%d)' % added, flush=True)
                if counts is None or not counts.get('ws'):
                    try: counts = data_counts(pg)   # after all three tabs loaded their data
                    except Exception as e: counts = {'error': str(e)[:100]}
                c.close()
        b.close()
    if srv: srv.shutdown()
    if base.startswith('https://') and not probe.get('ok'):
        bad.append('real tile check: %s status %s%s' % (probe.get('url'), probe.get('status'), (' ' + probe['detail']) if probe.get('detail') else ''))
    if measure:
        print(json.dumps({m: {k: sorted(v) for k, v in d.items()} for m, d in meas.items()}, indent=1)); print(counts); return [], counts, seen
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    json.dump({'base': base, 'cards': seen, 'counts': counts, 'bad': bad, 'known': sorted(set(KNOWN)), 'tiles': TILES, 'real_tile': probe}, open(os.path.join(ROOT, 'logs', 'design_lock.json'), 'w'), indent=1)
    open(os.path.join(ROOT, 'reports', 'design_lock.md'), 'w').write('# Card design lock (%s)\n\n%d cards checked, %d problems.\n\nData: %s\n\nTiles (w, mode, ok, failed): %s\n\nReal tile (one request, not a pan): %s %s%s\n\n%s\n\n## Known, not failing (%d)\n\n%s\n' % (
        base, seen, len(bad), json.dumps(counts), TILES, probe.get('status'), probe.get('url'), (' ' + probe['detail']) if probe.get('detail') else '', '\n'.join('- ' + x for x in bad[:300]), len(KNOWN), '\n'.join('- ' + x for x in sorted(set(KNOWN)))))
    base_c = LOCK.get('baseline_counts_v87', {})
    for k2, v in base_c.items():
        if isinstance(counts, dict) and isinstance(counts.get(k2), int) and counts[k2] < v * 0.97: bad.append('count %s dropped: %s vs v87 %s' % (k2, counts[k2], v))
    print('cards', seen, 'problems', len(bad), 'known', len(set(KNOWN)), 'tiles', TILES, 'real_tile', probe.get('status'), 'counts', counts)
    for x in bad[:40]: print(' FAIL', x)
    return bad, counts, seen

if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    bad, _, _ = run(a[0] if a else None, '--measure' in sys.argv)
    sys.exit(1 if bad else 0)
