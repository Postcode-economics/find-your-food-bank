#!/usr/bin/env python3
"""Full check of every food bank's OWN website, every refresh run (Dean, 22 Oct 2026).

Runs after build.py. For each distinct food bank website it fetches the homepage plus up to
2 linked help/contact/donate pages (polite: 1 request at a time per host, max 2 at a time on the
shared Trussell server *.foodbank.org.uk, 15 s timeouts, time budget) and checks:
 1. access: voucher / walk-in, against access.js (scripts/build_access.py). CLEAR flips (same wording on 2 runs)
    are applied to access.js automatically, kept in reports/access_tags.json and logged (reports/access_changes.json).
    Mixed / uncertain -> daily list. Unclear never gets a tag (= walk-ins welcome on the map).
 (Dean 22 Oct 10:33: confirmed closures + new food banks are auto-applied and logged too)
 2. opening-hours changes (seasonal / holiday notices, changed hours text) -> daily list
 3. closures (own site says closed) and new / removed food banks vs last run -> daily list
 4. dead sites and stale phones. A CLEAR new number (site shows exactly one UK number and the
    stored one is nowhere on it, seen on 2 runs in a row) is auto-applied (reports/phone_fixes.json)
    and logged; anything else -> daily list
 5. published stock / items-needed lists (new or changed) -> daily list
Nothing else is ever auto-applied. Fail safe: data.js is only rewritten if the item count is unchanged.
Stdlib only. DRY_RUN=1 -> no data.js write; SAMPLE=N -> only N websites."""
import concurrent.futures as cf, datetime, hashlib, html, json, os, re, sys, threading, time, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REP = os.path.join(ROOT, 'reports'); DATA = os.path.join(ROOT, 'data.full.js')
UA = {'User-Agent': 'Mozilla/5.0 (helpmap.uk food bank map; full daily check; +https://helpmap.uk)', 'Accept': 'text/html'}
TIMEOUT, BUDGET = 15, int(os.environ.get('BUDGET_S', 2400))
NOW = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
DAY = NOW.date().isoformat()

def rj(name, default):
    try: return json.load(open(os.path.join(REP, name), encoding='utf-8'))
    except Exception: return default
def wj(name, obj):
    p = os.path.join(REP, name); t = p + '.tmp'
    json.dump(obj, open(t, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); os.replace(t, p)

# ---------- polite fetching ----------
_locks, _last, _g = {}, {}, threading.Lock()
TRUSSELL = threading.Semaphore(2)
def _hostlock(h):
    with _g: return _locks.setdefault(h, threading.Lock())
def fetch(url):
    h = urllib.parse.urlparse(url).netloc.lower()
    sem = TRUSSELL if h.endswith('foodbank.org.uk') else None
    if sem: sem.acquire()
    try:
        with _hostlock(h):
            wait = 1.0 - (time.time() - _last.get(h, 0))
            if wait > 0: time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    body = r.read(1_500_000).decode(r.headers.get_content_charset() or 'utf-8', 'replace')
                    return {'ok': True, 'http': r.status, 'final_url': r.geturl(), 'html': body}
            except urllib.error.HTTPError as e: return {'ok': False, 'http': e.code, 'error': 'HTTP %d' % e.code}
            except Exception as e: return {'ok': False, 'http': None, 'error': type(e).__name__ + ': ' + str(e)[:80]}
            finally: _last[h] = time.time()
    finally:
        if sem: sem.release()

def text_of(h):
    h = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?i)<br\s*/?>|</(p|div|li|h\d|tr)>', '\n', h)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', h))
    return '\n'.join(re.sub(r'[ \t\xa0]+', ' ', l).strip() for l in t.split('\n') if l.strip())

SUB = re.compile(r'get[- ]?help|need[- ]?help|referr|voucher|how[- ]?(it|we)[- ]?work|contact|donat|items|shopping[- ]?list|opening|find[- ]?us|locations|centres', re.I)
def links(h, base):
    out = []
    for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', h):
        u = urllib.parse.urljoin(base, href.strip())
        if urllib.parse.urlparse(u).netloc.lower() != urllib.parse.urlparse(base).netloc.lower(): continue
        if re.search(r'\.(pdf|jpe?g|png|docx?)$', u, re.I): continue
        if SUB.search(u) or SUB.search(re.sub('<[^>]+>', '', label)):
            if u not in out and u.rstrip('/') != base.rstrip('/'): out.append(u)
    rank = lambda u: 0 if re.search(r'help|referr|voucher', u, re.I) else 1 if re.search(r'donat|items|list', u, re.I) else 2
    return sorted(out, key=rank)[:2]

# ---------- signals ----------
V_STRONG = re.compile(r"(you('ll| will)? need|require[sd]?|need) (a |an )?(food ?bank |e-?)?(voucher|referral)|"
    r"(voucher|referral)s? (is |are )?(needed|required|essential)|by (voucher|referral) only|referral only|"
    r"(must|need to|will need to) be referred|cannot (accept|serve|help).{0,30}without a (voucher|referral)|no walk[- ]?ins?", re.I)
W_STRONG = re.compile(r"no (voucher|referral)s? (is |are )?(needed|required|necessary)|without (a |the need for a )?(voucher|referral)|"
    r"walk[- ]?ins? (are |is )?(welcome|accepted)|just (turn|come|drop) (up|in|along)|self[- ]?referr?(al|ing|ed)?|"
    r"(don'?t|do not|won'?t) need (a |to have a |an? )?(food ?bank )?(voucher|referral)", re.I)  # self-referral counts as walk-in (Dean; same as build_access.py)
def access(t):
    v = [m.group(0) for m in V_STRONG.finditer(t) if not re.match(r'no (voucher|referral)', m.group(0), re.I)
         and not re.search(r"(\bno|without|don'?t|do not|not)\s+(a |an |any )?(food ?bank )?$", t[max(0, m.start() - 25):m.start()], re.I)]
    w = [m.group(0) for m in W_STRONG.finditer(t)]
    if v and not w: return 'voucher', v[:2]
    if w and not v: return 'walkin', w[:2]
    if v and w: return 'mixed', (v[:1] + w[:1])
    return 'unclear', []
SEASON = re.compile(r"(christmas|xmas|new year|easter|bank holiday|half[- ]term|summer|winter|festive)[^.\n]{0,80}(clos|open|hours|times|session)|"
    r"(clos|open|hours|times)[^.\n]{0,60}(christmas|xmas|new year|easter|bank holiday|half[- ]term|festive)|"
    r"(new|change[sd]? to( our)?|revised|temporary|updated) (opening )?(hours|times)", re.I)
PERM_CLOSED = re.compile(r"(food ?bank|pantry|we) (has|have) (now )?(permanently )?closed( down)?\b(?! (on|for|over|during|until|till|from|between))|permanently closed|"
    r"no longer (operating|running)( a| the| our)? ?(food ?bank)?|(has|have) ceased (operat|trading)|closed (its|our) doors (for good|permanently)", re.I)
CLOSED = re.compile(r"(food ?bank|we) (has|have) (now )?(permanently )?closed|permanently closed|no longer (operat|running|open)|"
    r"(has|have) ceased|closed (its|our) doors|temporarily closed|is closed until", re.I)
NEEDS = re.compile(r"(items? (we )?(urgently |currently )?need(ed)?|urgently need|running low|shopping list|we are short of|current needs|most needed)", re.I)
PHONE = re.compile(r'(?<!\d)(?:\+44\s?\(?0?\)?|0)(?:\d[\s-]?){9,10}(?!\d)')
DAYS = re.compile(r'\b(mon|tues?|wed(nes)?|thur?s?|fri|sat(ur)?|sun)(day)?s?\b[^\n]{0,60}\d{1,2}([.:]\d{2})?\s*(am|pm)?\s*[-–to]+\s*\d', re.I)
def norm_phone(p):
    d = re.sub(r'\D', '', p or '')
    if d.startswith('44'): d = '0' + d[2:]
    if d.startswith('00'): d = d[1:]
    return d if len(d) == 11 and d[0] == '0' else ''
def snippet(t, rx, n=220):
    m = rx.search(t)
    if not m: return ''
    a = max(0, m.start() - 40); return re.sub(r'\s+', ' ', t[a:a + n]).strip()
def needs_list(t):
    m = NEEDS.search(t)
    if not m: return ''
    seg = t[m.start():m.start() + 700].split('\n')[:14]
    return ' | '.join(s.strip() for s in seg if 2 < len(s.strip()) < 80)[:500]

def check_site(url):
    home = fetch(url)
    if not home['ok'] and url.startswith('http://'): home = fetch('https://' + url[7:])  # many sites redirect anyway
    res = {'url': url, 'checked_at': NOW.isoformat(), 'http': home.get('http')}
    if not home['ok']: res.update(ok=False, error=home['error']); return res
    pages = [(home['final_url'], home['html'])]
    for u in links(home['html'], home['final_url']):
        r = fetch(u)
        if r['ok']: pages.append((r['final_url'], r['html']))
    t = '\n'.join(text_of(h) for _, h in pages)
    a, ev = access(t)
    hours = sorted({re.sub(r'\s+', ' ', m.group(0)).lower() for m in DAYS.finditer(t)})[:30]
    phones = sorted({p for p in (norm_phone(x) for x in PHONE.findall(t)) if p and not p.startswith(('0800', '0808', '0300', '0345', '0844', '0845', '0870', '0330')) or p.startswith(('01', '02', '07'))} - {''})
    tel = sorted({p for p in (norm_phone(urllib.parse.unquote(x)) for _, h in pages for x in re.findall(r'href=["\']tel:([^"\']+)', h, re.I)) if p})
    res.update(tel=tel[:4], ok=True, final_url=home['final_url'], pages=[u for u, _ in pages], access=a, access_evidence=ev,
               hours_hash=hashlib.sha1('\n'.join(hours).encode()).hexdigest()[:12] if hours else '', hours_sample=hours[:4],
               seasonal=snippet(t, SEASON), closed=snippet(t, CLOSED), perm_closed=snippet(t, PERM_CLOSED), phones=phones[:8], needs=needs_list(t))
    return res

# ---------- main ----------
def load_data():
    s = open(DATA, encoding='utf-8').read(); return s, json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))

ACC = os.path.join(ROOT, 'access.js')
def load_access():
    try: s = open(ACC, encoding='utf-8').read(); return json.loads(s[s.index('{'):s.rindex('}') + 1])
    except Exception: return {}

def phone_locked(i):
    """Point 1 (Dean, 24 Oct 2026): hand-checked or locked phones are never overwritten automatically."""
    return bool(i.get('phone_checked') or i.get('locked'))

def apply_phone_fixes(by_site, fixes, flag):
    """Apply auto phone fixes, skipping locked/hand-checked entries; skipped changes go to Dean's review list."""
    n = 0
    for u, lst in by_site.items():
        f = fixes.get(u)
        if not f: continue
        for i in lst:
            if norm_phone(i.get('phone')) != f['old']: continue
            if phone_locked(i):
                flag(u + '|' + i.get('id', ''), 'phone change skipped (locked / hand-checked)', name=i.get('name', ''), id=i.get('id', ''), website=u, stored=i.get('phone'), proposed=f['new'], source=f.get('source', ''), note='not applied because this phone is marked phone_checked or locked; change it by hand if right')
                continue
            i['phone'] = i['tel'] = f['new']; i['phone_source'] = f['source']; n += 1
    return n

def main():
    os.makedirs(REP, exist_ok=True)
    raw, d = load_data(); items = d['items']; n0 = len(items)
    state = rj('full_check_state.json', {'sites': {}, 'ids': []})
    tags = rj('access_tags.json', {})       # pin id -> {"tag": "voucher"|"walkin", "since", "evidence", "source", "was"} (auto flips)
    acc = load_access()
    CLP = os.path.join(ROOT, 'overrides', 'foodbank_closed.json')
    try: closed_raw = json.load(open(CLP, encoding='utf-8'))
    except Exception: closed_raw = {}
    closed_ov, closed_hold, remove = {}, set(closed_raw.get('_hold_for_review', [])), set()
    for x, t in tags.items():
        if x in acc: acc[x] = t['tag']   # build_access.py regenerated access.js from the CSVs; re-apply our flips
    fixes = rj('phone_fixes.json', {})      # website -> {"old", "new", "since", "source"}
    changes = rj('access_changes.json', [])
    review = rj('daily_review.json', {})
    today = review.get(DAY, {'date': DAY, 'runs': [], 'items': {}}); review = {k: v for k, v in review.items() if k >= (NOW.date() - datetime.timedelta(days=14)).isoformat()}
    flag = lambda key, cat, **kw: today['items'].__setitem__(cat + '|' + key, dict(category=cat, first_flagged=today['items'].get(cat + '|' + key, {}).get('first_flagged', NOW.isoformat()), **kw))
    by_site = {}; by_id = {i['id']: i for i in items}
    for i in items:
        w = (i.get('website') or '').strip()
        if w.startswith('http'): by_site.setdefault(w, []).append(i)
    sites = sorted(by_site)
    if os.environ.get('SAMPLE'): sites = [u for u in sites if u.startswith('https') and 'foodbank.org.uk' not in u][:int(os.environ['SAMPLE'])]
    # (3) new / removed food banks vs last run
    ids = sorted(i['id'] for i in items if i['type'] == 'foodbank'); prev_ids = set(state.get('ids') or [])
    if prev_ids:
        for x in sorted(set(ids) - prev_ids):
            i = next(j for j in items if j['id'] == x)
            e = dict(when=NOW.isoformat(), id=x, website=i.get('website') or '', name=i['name'], kind='new food bank', old='not on map', new='added (%s)' % (i.get('postcode') or ''), source=(i.get('own_site_check') or {}).get('final_url') or i.get('website') or i.get('givefood') or '')
            changes.insert(0, e); log.append(e)
        for x in sorted(prev_ids - set(ids)):
            e = dict(when=NOW.isoformat(), id=x, website='', name=x, kind='removed', old='on map', new='gone (no longer in the feed / closed on own site / excluded)', source='logs/foodbank_closed.json'); changes.insert(0, e); log.append(e)
    # fetch everything (time-boxed; whatever is left is reported, not guessed)
    t0 = time.time(); results = {}
    def job(u):
        if time.time() - t0 > BUDGET: return u, {'url': u, 'ok': None, 'error': 'time budget reached - not checked this run'}
        try: return u, check_site(u)
        except Exception as e: return u, {'url': u, 'ok': False, 'error': 'check error: %r' % e}
    with cf.ThreadPoolExecutor(12) as ex:
        for u, r in ex.map(job, sites): results[u] = r
    log = []; stats = dict(sites=len(sites), ok=0, failed=0, skipped=0, voucher=0, walkin=0, mixed=0, unclear=0, flips=0, phone_fixes=0, closures=0)
    for u in sites:
        r, prev = results[u], state['sites'].get(u, {}); names = sorted({i['foodbank'] for i in by_site[u]}); name = names[0]
        if r.get('ok') is None: stats['skipped'] += 1; continue
        if not r['ok']:
            stats['failed'] += 1; r['fail_runs'] = prev.get('fail_runs', 0) + 1
            for k in ('access', 'hours_hash', 'needs', 'phones', 'seasonal', 'closed'): r[k] = prev.get(k)
            r['perm_closed'] = None  # a failed fetch never confirms a closure
            if r['fail_runs'] >= 2: flag(u, 'dead or unreachable website', name=name, website=u, error=r['error'], failed_runs=r['fail_runs'], phone=by_site[u][0].get('phone'), note='site failed %d runs in a row - check contact details' % r['fail_runs'])
            state['sites'][u] = {k: r.get(k) for k in ('checked_at', 'http', 'error', 'access', 'hours_hash', 'needs', 'phones', 'seasonal', 'closed', 'perm_closed', 'fail_runs')}; continue
        stats['ok'] += 1; r['fail_runs'] = 0; stats[r['access']] += 1
        # (1) access - per pin, against access.js (hand-read CSVs + earlier auto flips). A flip needs the
        # same clear own-site result on 2 runs in a row; unclear never changes anything (= walk-ins welcome).
        curs = {i['id']: acc.get(i['id'], 'unconfirmed') for i in by_site[u] if i['id'] in acc}
        if r['access'] in ('voucher', 'walkin'):
            todo = [x for x, c in curs.items() if c != r['access']]
            trus = [x for x in todo if r['access'] == 'walkin' and by_id[x].get('network') == 'Trussell']
            if trus:  # Trussell = voucher (Dean); walk-in wording on a Trussell site is a flag, never an automatic flip
                flag(u, 'Trussell site with walk-in wording', name=name, website=u, current_tag='voucher', evidence=r['access_evidence'], note='left as voucher - please check')
                todo = [x for x in todo if x not in trus]
            if todo and prev.get('access') == r['access']:
                for x in todo:
                    entry = dict(when=NOW.isoformat(), id=x, website=u, name=name, old=curs[x], new=r['access'], evidence=r['access_evidence'], source=r['final_url'])
                    changes.insert(0, entry); tags[x] = dict(tag=r['access'], since=DAY, evidence=r['access_evidence'], source=r['final_url'], was=curs[x]); acc[x] = r['access']
                today['items'].pop('access flip pending (confirms next run)|' + u, None)
                log.append(dict(name=name, website=u, old=', '.join(sorted(set(curs[x] for x in todo))), new=r['access'] + ' (%d pins)' % len(todo), source=r['final_url'])); stats['flips'] += len(todo)
            elif todo:
                flag(u, 'access flip pending (confirms next run)', name=name, website=u, current_tag=', '.join(sorted(set(curs[x] for x in todo))), evidence=r['access_evidence'], note='clear %s wording found; applied automatically if seen again next run' % r['access'])
        elif r['access'] == 'mixed':
            flag(u, 'access mixed', name=name, website=u, current_tag=', '.join(sorted(set(curs.values()))) or 'unconfirmed', evidence=r['access_evidence'], note='site mentions both voucher and walk-in - left as is, please decide')
        elif 'voucher' in curs.values() and prev.get('access') == 'voucher':
            flag(u, 'access now uncertain', name=name, website=u, current_tag='voucher', note='voucher wording no longer found - tag kept until you decide')
        # (2) hours
        if r['seasonal'] and r['seasonal'] != prev.get('seasonal'): flag(u, 'seasonal/holiday hours notice', name=name, website=u, text=r['seasonal'])
        if prev.get('hours_hash') and r['hours_hash'] and r['hours_hash'] != prev['hours_hash']:
            flag(u, 'opening hours changed on own site', name=name, website=u, before=prev.get('hours_sample'), now=r['hours_sample'])
        # (3) closure: clear permanent wording on 2 runs in a row -> removed automatically (overrides/foodbank_closed.json),
        # unless Dean put the pin on _hold_for_review. Temporary / holiday closures stay flags.
        if r['perm_closed'] and prev.get('perm_closed'):
            ids_ = [i['id'] for i in by_site[u] if i['id'] not in closed_hold]
            for x in ids_:
                closed_ov[x] = dict(url=r['final_url'], evidence=r['perm_closed'], confirmed='auto: own site said permanently closed on 2 runs in a row (scripts/full_check.py %s)' % DAY)
                remove.add(x)
            today['items'].pop('closure pending (confirms next run)|' + u, None)
            if ids_:
                e = dict(when=NOW.isoformat(), website=u, name=name, kind='closure', old='on map (%d pins)' % len(ids_), new='removed - own site says closed', source=r['final_url'], evidence=r['perm_closed'])
                changes.insert(0, e); log.append(e); stats['closures'] += 1
            if len(ids_) < len(by_site[u]): flag(u, 'closure on hold (your hold list)', name=name, website=u, text=r['perm_closed'])
        elif r['perm_closed']: flag(u, 'closure pending (confirms next run)', name=name, website=u, text=r['perm_closed'], note='removed automatically if the wording is still there next run')
        elif r['closed'] and r['closed'] != prev.get('closed'): flag(u, 'own site mentions closure (temporary/unclear)', name=name, website=u, text=r['closed'])
        # (4) phones
        stored = {norm_phone(i.get('phone')) for i in by_site[u]} - {''}
        if stored and r['phones'] and not (stored & set(r['phones'])):
            if len(r['phones']) == 1 and r.get('tel') == r['phones'] and prev.get('phones') == r['phones'] and u not in fixes:
                new = r['phones'][0]; old = sorted(stored)[0]
                fixes[u] = dict(old=old, new=new, since=DAY, source=r['final_url']); stats['phone_fixes'] += 1
                today['items'].pop('phone number not on own site|' + u, None)
                e = dict(when=NOW.isoformat(), website=u, name=name, kind='phone', old=old, new=new, source=r['final_url']); changes.insert(0, e); log.append(e)
            elif u not in fixes:
                flag(u, 'phone number not on own site', name=name, website=u, stored=sorted(stored), on_site=r['phones'], note='only a single clickable number seen on 2 runs is auto-applied; this one is not clear')
        # (5) items needed
        if r['needs'] and prev.get('checked_at') and r['needs'] != prev.get('needs'): flag(u, 'items-needed list ' + ('updated' if prev.get('needs') else 'published'), name=name, website=u, list=r['needs'])
        state['sites'][u] = {k: r.get(k) for k in ('checked_at', 'http', 'final_url', 'access', 'hours_hash', 'hours_sample', 'seasonal', 'closed', 'perm_closed', 'phones', 'tel', 'needs', 'fail_runs')}
    if not os.environ.get('SAMPLE'): state['ids'] = ids
    state['last_run'] = NOW.isoformat()
    # apply phone fixes to data.js (every run, since build.py rebuilds from the feed)
    apply_phone_fixes(by_site, fixes, flag)
    today['runs'].append(dict(at=NOW.isoformat(), **stats)); review[DAY] = today
    wj('full_check_state.json', state); wj('access_tags.json', tags); wj('phone_fixes.json', fixes); wj('access_changes.json', changes[:2000]); wj('daily_review.json', review)
    write_md(today, log, stats)
    print('full check:', json.dumps(stats))
    if remove:
        items[:] = [i for i in items if i['id'] not in remove]
        for x in remove: acc.pop(x, None)
    if len(items) != n0 - len(remove) or len(remove) > 30: print('FAIL SAFE: unexpected item count / too many closures (%d), nothing written' % len(remove)); sys.exit(1)
    if os.environ.get('DRY_RUN') or os.environ.get('SAMPLE'): print('DRY RUN/SAMPLE: data.js not written'); return
    out = raw[:raw.index('=') + 1] + json.dumps(d) + ';'
    json.loads(out[out.index('=') + 1:].rstrip(';'))
    t = DATA + '.tmp'; open(t, 'w', encoding='utf-8').write(out); os.replace(t, DATA)
    import compact; compact.main()  # browser-facing compact data.js
    if closed_ov:
        closed_raw.update(closed_ov); t = CLP + '.tmp'
        json.dump(closed_raw, open(t, 'w', encoding='utf-8'), indent=2, ensure_ascii=False); os.replace(t, CLP)
    if acc:
        t = ACC + '.tmp'; open(t, 'w', encoding='utf-8').write('window.FB_ACCESS=' + json.dumps(acc, separators=(',', ':')) + ';\n'); os.replace(t, ACC)

def write_md(today, log, stats):
    L = ['# Daily review - food banks - %s' % today['date'], '',
         'Generated by scripts/full_check.py on every refresh run. Auto-applied (Dean, 22 Oct 10:33): clear access flips, clear phone fixes, confirmed closures (own site says permanently closed on 2 runs running) and new food banks - all logged below and in reports/access_changes.json. Only uncertain or mixed cases are listed for Dean.', '',
         '## Runs today', '', '| run (UTC) | sites | checked | failed | not reached | voucher | walk-in | mixed | unclear | access flips | phone fixes | closures |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in today['runs']: L.append('| %s | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d | %d |' % (r['at'][11:16], r['sites'], r['ok'], r['failed'], r['skipped'], r['voucher'], r['walkin'], r['mixed'], r['unclear'], r['flips'], r['phone_fixes'], r.get('closures', 0)))
    L += ['', '## Auto-applied this run', '']
    L += ['- %s**%s** (%s): %s → %s — %s' % ((e.get('kind') + ': ') if e.get('kind') else 'access: ', e['name'], e['website'], e['old'], e['new'], e['source']) for e in log] or ['- none']
    cats = {}
    for v in today['items'].values(): cats.setdefault(v['category'], []).append(v)
    L += ['', '## For Dean to review (%d)' % len(today['items'])]
    for c in sorted(cats):
        L += ['', '### %s (%d)' % (c, len(cats[c])), '']
        for v in sorted(cats[c], key=lambda v: v.get('name') or ''):
            extra = '; '.join('%s: %s' % (k, v[k] if not isinstance(v[k], list) else ' / '.join(map(str, v[k]))) for k in ('text', 'list', 'evidence', 'stored', 'on_site', 'error', 'before', 'now', 'current_tag', 'note') if v.get(k))
            L.append('- **%s** %s — %s' % (v.get('name') or v.get('id'), v.get('website') or '', extra[:400]))
    open(os.path.join(REP, 'daily_review.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')

if __name__ == '__main__': main()
