#!/usr/bin/env python3
"""Full check of every food bank's OWN website, every refresh run (Dean, 22 Oct 2026).

Runs after build.py. For each distinct food bank website it fetches the homepage plus up to
2 linked help/contact/donate pages (polite: 1 request at a time per host, max 2 at a time on the
shared Trussell server *.foodbank.org.uk, 15 s timeouts, time budget) and checks:
 1. access: voucher / walk-in, against access.js (scripts/build_access.py). CLEAR flips (same wording on 2 runs)
    are applied to access.js automatically, kept in reports/access_tags.json and logged (reports/access_changes.json).
    Mixed / uncertain -> daily list. Unclear never gets a tag (= walk-ins welcome on the map).
 (Dean 25 Oct 2026: confirmed closures and new food banks are NOT auto-applied; they go to reports/pending_dean.md)
 2. opening-hours changes (seasonal / holiday notices, changed hours text) -> daily list
 3. closures (own site says closed) and new / removed food banks vs last run -> daily list
 4. dead sites and stale phones. A CLEAR new number is auto-applied (reports/phone_fixes.json) only through the
    strict gate (Dean, 28 Oct 2026; phone_gate_reasons): read on the organisation's own host, exactly one clickable
    number there (no conflicting own-site number), identical on 2 separate runs, not undone by Dean. Each change is
    logged once in reports/phone_auto_applied.json with its source URL and an undo command (scripts/phone_revert.py),
     including when that number is a named person's, with the role the page gives
     (rule 21, Dean 26 Oct 2026), unless that listing is in overrides/phone_baseline.json: then it is held
     for Dean with its source and not applied. Until that file exists, every existing listing is held the
     same way. Anything else -> daily list, with the reason recorded
 5. published stock / items-needed lists (new or changed) -> daily list
Nothing else is ever auto-applied. Fail safe: data.js is only rewritten if the item count is unchanged.
Opening times (Rule 27): each listing is checked against the exact source URL on the card, live.
A redirect to another page is unclear. Plain HTML with no complete day/time set is rendered in a
headless browser. A listing is verified only when every recorded day and time is on that page, with
the evidence quote stored. A failed, skipped, or unconfirmable read is not left as the previous
verified hours. Access flips and phone fixes still need the same result on 2 runs. Per-host gap stays
2 seconds, one request at a time per host. DRY_RUN=1 -> no data.js write; SAMPLE=N -> only N websites."""
import concurrent.futures as cf, datetime, hashlib, html, json, os, re, sys, threading, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import learning  # self-learning order (Dean 25 Oct 08:01)
import discover
import phone_lock  # frozen listing numbers are never auto-changed (Dean, 27 Oct 2026)
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
MIN_GAP, ERR_LIMIT, PAUSE = 2.0, 3, 600  # point 21: ~1 request / 2 s per domain; 3 errors in a row pause that domain 10 min
_errs, _paused = {}, {}
def _note(h, ok):
    if ok: _errs[h] = 0; return
    _errs[h] = _errs.get(h, 0) + 1
    if _errs[h] >= ERR_LIMIT: _paused[h] = time.time() + PAUSE; _errs[h] = 0

def _polite(url, loader):
    """One request at a time per host, then MIN_GAP. Shared by the plain fetch and the headless render."""
    h = urllib.parse.urlparse(url).netloc.lower()
    sem = TRUSSELL if h.endswith('foodbank.org.uk') else None
    if sem: sem.acquire()
    try:
        with _hostlock(h):
            if _paused.get(h, 0) > time.time(): return {'ok': False, 'http': None, 'error': 'source paused for 10 min after %d errors in a row' % ERR_LIMIT}
            wait = MIN_GAP - (time.time() - _last.get(h, 0))
            if wait > 0: time.sleep(wait)
            try:
                out = loader(url)
            except Exception as e:
                _note(h, False); out = {'ok': False, 'http': None, 'error': type(e).__name__ + ': ' + str(e)[:80]}
            finally:
                _last[h] = time.time()
            return out
    finally:
        if sem: sem.release()
def _urllib_load(url):
    import rate_ledger
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(1_500_000).decode(r.headers.get_content_charset() or 'utf-8', 'replace')
            _note(urllib.parse.urlparse(url).netloc.lower(), True); rate_ledger.LEDGER.record(url, r.status)
            return {'ok': True, 'http': r.status, 'final_url': r.geturl(), 'html': body}
    except urllib.error.HTTPError as e:
        _note(urllib.parse.urlparse(url).netloc.lower(), False); rate_ledger.LEDGER.record(url, e.code)
        return {'ok': False, 'http': e.code, 'error': 'HTTP %d' % e.code}
    except Exception:
        rate_ledger.LEDGER.record(url, None); raise
def fetch(url):
    import rate_ledger
    if not rate_ledger.LEDGER.allow(url):
        return {'ok': None, 'http': 429, 'error': 'paused this run after HTTP 429 - still due on a later scheduled run'}
    return _polite(url, _urllib_load)

def text_of(h):
    h = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', h)
    h = re.sub(r'(?i)<br\s*/?>|</(p|div|li|h\d|tr)>', '\n', h)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', h))
    return '\n'.join(re.sub(r'[ \t\xa0]+', ' ', l).strip() for l in t.split('\n') if l.strip())

SUB = re.compile(r'get[- ]?help|need[- ]?help|referr|voucher|how[- ]?(it|we)[- ]?work|contact|donat|items|shopping[- ]?list|opening|find[- ]?us|locations|centres', re.I)
def links(h, base, phone_pass=False):
    out = []
    for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', h):
        u = urllib.parse.urljoin(base, href.strip())
        if urllib.parse.urlparse(u).netloc.lower() != urllib.parse.urlparse(base).netloc.lower(): continue
        if re.search(r'\.(pdf|jpe?g|png|docx?)$', u, re.I): continue
        if SUB.search(u) or SUB.search(re.sub('<[^>]+>', '', label)):
            if u not in out and u.rstrip('/') != base.rstrip('/'): out.append(u)
    rank = lambda u: 0 if re.search(r'help|referr|voucher', u, re.I) else 1 if re.search(r'donat|items|list', u, re.I) else 2
    if phone_pass:  # centres' own lines sit on the locations page; read it first so a centre number is never taken for the site's
        rank = lambda u, r=rank: -1 if re.search(r'locations|centres', u, re.I) else r(u)
    return sorted(out, key=rank)[:2]
def is_subpage(url):
    """The listing's website is one page on a bigger site (a church's food bank page): only that page is read."""
    return urllib.parse.urlparse(url or '').path.strip('/') != ''

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

def own_site_misses_stored(stored, site_phones):
    """True when the own page lists numbers and none of them is the stored one.
    A page that still shows the stored number, even among others, does not replace it."""
    return bool(stored and site_phones and not (set(stored) & set(site_phones)))

# Strict gate for automatic phone changes (Dean, 28 Oct 2026): the same rules as the refresh times gate.
PHONE_LOG = 'phone_auto_applied.json'                         # reports/: every automatic phone change, once
PHONE_UNDONE = os.path.join('overrides', 'phone_auto_undone.json')  # website -> number Dean undid; never re-applied
def _host(u):
    return urllib.parse.urlparse(u or '').netloc.lower().split(':')[0].removeprefix('www.')
def own_host(site, u):
    a, b = _host(site), _host(u)
    return bool(a and b and (a == b or b.endswith('.' + a) or a.endswith('.' + b)))
def phone_gate_reasons(u, r, prev, undone=None):
    """Reasons a proposed own-site phone change must be held for Dean. Empty = it may apply (tests/test_phone_gate.py)."""
    why = []
    phones = r.get('phones') or []
    if len(phones) != 1 or r.get('tel') != phones: why.append('not exactly one clickable number on the own site (another own-site number conflicts, or none is clickable)')
    if not own_host(u, r.get('final_url')) or not all(own_host(u, p) for p in (r.get('pages') or [])):
        why.append("not read on the organisation's own host")
    if prev.get('phones') != phones or not own_host(u, prev.get('final_url')) or not prev.get('checked_at') or prev.get('checked_at') == r.get('checked_at'):
        why.append('number not read identically on 2 separate runs yet')
    if phones and phones[0] in undone_numbers(undone, u): why.append('this change was undone by Dean; not re-applied')
    if r.get('fb_mention') is False: why.append('the page does not mention a food bank or the listing name')
    if phones and (r.get('phone_context') or {}).get(phones[0]): why.append(r['phone_context'][phones[0]])
    return why
def undone_numbers(undone, key):
    """Every number Dean undid for this website or pin. Older files hold one number per key, newer ones a list."""
    v = (undone or {}).get(key)
    return {norm_phone(x) or x for x in (v if isinstance(v, list) else [v]) if x}
def _kind(i): return i.get('type') or 'foodbank'
def site_phone_plan(pins, new, centre_phones=None):
    """(pins a site-level number may change, reason held). A site-level number only ever changes the single food bank pin,
    and only when no location pin shares its number and the food bank's own centre block does not give another line.
    Location pins change only from their own centre block (centre_phone_plan)."""
    fbs = [i for i in pins if _kind(i) == 'foodbank']
    if len(fbs) != 1: return [], 'site-level number: %d food bank pins on this website, not exactly one' % len(fbs)
    fb = fbs[0]; old = norm_phone(fb.get('phone'))
    if not old: return [], 'site-level number: the food bank pin has no stored number to replace'
    if old == new: return [], ''
    if any(_kind(i) == 'location' and norm_phone(i.get('phone')) == old for i in pins):
        return [], 'site-level number: a location pin shares the food bank number; location pins change only from their own centre block'
    own = (centre_phones or {}).get(fb.get('id')) or {}
    if norm_phone(own.get('phone')) and norm_phone(own.get('phone')) != new:
        return [], "the food bank's own centre block on its locations page gives %s; the centre's own line wins" % own['phone']
    return [fb], ''
def centre_phone_plan(pin, rec):
    """(new number, reason held) for one location pin from its own centre block, matched by postcode, same on 2 runs."""
    import own_locations
    if not isinstance(rec, dict) or not rec.get('phones'): return '', ''
    if len(rec['phones']) != 1: return '', 'centre block gives %d numbers, not exactly one' % len(rec['phones'])
    if (rec.get('postcode') or '').replace(' ', '') != (pin.get('postcode') or '').replace(' ', ''):
        return '', 'centre block postcode %s does not match the pin (%s)' % (rec.get('postcode'), pin.get('postcode'))
    new = norm_phone(rec['phone'])
    if not new or new == norm_phone(pin.get('phone')): return '', ''
    if not own_locations.centre_phone_confirmed(rec): return '', 'centre block number not read identically on 2 separate runs yet'
    return new, ''
HOST_PAGE = re.compile(r'church|parish|chapel|diocese|cathedral|rcdow|minster|abbey|anglican|methodist|baptist', re.I)
def fix_gate_reasons(key, f, pins, fixes, all_items=(), undone=None, centre_phones=None):
    """Reasons a stored phone fix (reports/phone_fixes.json) must be held this run. Empty = it may be written.
    Every fix goes through this on every run, including fixes recorded before the gate existed."""
    why = []
    new = norm_phone(f.get('new'))
    if not new: return ['proposed number is not a UK number']
    if new in undone_numbers(undone, key): why.append('this change was undone by Dean; not re-applied')
    if phone_rule.is_dean(new): why.append(phone_rule.DEAN_REASON)
    others = sorted(k for k, g in (fixes or {}).items() if k != key and norm_phone((g or {}).get('new')) == new)
    if others: why.append('the same number is proposed for another listing too (%s): a shared office/diocese line, not this food bank\'s own' % ', '.join(others))
    mine = {i.get('id') for i in pins}
    shared = sorted({i.get('id') for i in all_items or () if i.get('id') not in mine and norm_phone(i.get('phone')) == new and (i.get('website') or '') != key})
    if shared: why.append('the number is already listed for another place (%s)' % ', '.join(shared[:3]))
    if f.get('centre_id'):
        pin = next((i for i in pins if i.get('id') == f['centre_id']), None)
        rec = (centre_phones or {}).get(f['centre_id'])
        if not pin or _kind(pin) != 'location': why.append('centre fix: pin %s not found as a location pin' % f['centre_id'])
        elif not isinstance(rec, dict) or norm_phone(rec.get('phone')) != new or (rec.get('postcode') or '').replace(' ', '') != (pin.get('postcode') or '').replace(' ', ''):
            why.append("centre fix: the pin's own centre block (matched by postcode) no longer gives this number")
        return why
    targets, reason = site_phone_plan(pins, new, centre_phones)
    if reason: why.append(reason)
    if is_subpage(key) and HOST_PAGE.search(key) and f.get('fb_mention') is not True:
        why.append('website is a page on a host church/parish site and the fix records no food bank mention on that page')
    return why
def log_phone_changes(applied, path=None):
    """One undo-log entry per (website, new number). A fix re-applied on a later run (build.py rebuilds from the feed)
    is not logged again. Revert with scripts/phone_revert.py <website>."""
    path = path or os.path.join(REP, PHONE_LOG)
    try: log = json.load(open(path, encoding='utf-8'))
    except Exception: log = []
    have = {(e.get('website'), e.get('new')) for e in log if not e.get('reverted')}
    added = []
    for u, f in applied:
        if (u, f['new']) in have: continue
        have.add((u, f['new']))
        e = dict(website=u, old=f.get('old'), new=f['new'], source_url=f.get('source') or '', since=f.get('since'),
                 first_run_at=f.get('first_run_at'), second_run_at=f.get('second_run_at'), revert='python scripts/phone_revert.py ' + u)
        log.append(e); added.append(e)
    if added:
        t = path + '.tmp'; json.dump(log, open(t, 'w', encoding='utf-8'), indent=1, ensure_ascii=False); os.replace(t, path)
    return added
def snippet(t, rx, n=220):
    m = rx.search(t)
    if not m: return ''
    a = max(0, m.start() - 40); return re.sub(r'\s+', ' ', t[a:a + n]).strip()
def needs_list(t):
    m = NEEDS.search(t)
    if not m: return ''
    seg = t[m.start():m.start() + 700].split('\n')[:14]
    return ' | '.join(s.strip() for s in seg if 2 < len(s.strip()) < 80)[:500]

_robots_cache = {}
def _robots_text(url):
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.netloc: return "", "/"
    base = "%s://%s" % (parts.scheme, parts.netloc)
    if base not in _robots_cache:
        try:
            rb = fetch(base + "/robots.txt")
            _robots_cache[base] = (rb.get("html") or "") if rb.get("http") == 200 else ""
        except Exception:
            _robots_cache[base] = ""
    return _robots_cache[base], parts.path or "/"

UNCLEAR_LINE = 'Opening times not listed. Call before you go.'
def drop_saved_hours(r):
    """No live page, so no hours reading. The previous run's hash is not a source and is not kept."""
    r['hours_hash'] = ''; r['hours_sample'] = []; r['seasonal'] = None
    r['hours_status'] = 'unclear'; r['hours_evidence'] = ''
    return r
def listing_source_url(item):
    """The source URL the card shows, or '' when the card does not show one."""
    ot = item.get('opening_times') if isinstance(item.get('opening_times'), dict) else {}
    u = ot.get('source_url') if isinstance(ot, dict) else ''
    if isinstance(u, str) and u.startswith('http') and 'helpmap.uk' not in u: return u
    return ''
def hours_verdict(item, page):
    """Verified only when the page we read is the listing's source URL and every recorded day and time
    is on it. The evidence quote is copied from that page. Anything else is unclear, with no hours filled in."""
    src = listing_source_url(item)
    out = {'status': 'unclear', 'evidence': '', 'source_url': src, 'final_url': (page or {}).get('final_url') or '',
           'rendered': bool((page or {}).get('rendered')), 'note': ''}
    if not src:
        out['note'] = 'unclear: no source url on the listing. ' + UNCLEAR_LINE
        return out
    if not page or not page.get('ok'):
        out['note'] = 'unclear: live source page could not be opened (%s). %s' % ((page or {}).get('error') or 'no response', UNCLEAR_LINE)
        return out
    landed = page.get('final_url') or ''
    if not discover.source_page_ok(src, landed):
        out['note'] = 'unclear: source url redirected to a different page (%s). %s' % (landed, UNCLEAR_LINE)
        return out
    text = page.get('text') or ''
    table = discover.shown_table(item.get('opening_times'))
    if not table:
        out['note'] = 'unclear: the listing has no day table that can be checked against the page. ' + UNCLEAR_LINE
        return out
    ok, quote = discover.live_hours_ok(table, text, item.get('postcode'))
    if not ok or not quote or quote not in text:
        out['note'] = 'unclear: recorded days or times could not be confirmed on the page. ' + UNCLEAR_LINE
        return out
    out.update(status='verified', evidence=quote, note='every recorded day and time is on the source page')
    return out
def read_source(item, fetch=None, render=None):
    """Live read of the listing's own source URL. The website homepage is not a substitute.
    Plain HTML is enough when it already contains a complete day/time set. Otherwise render once.
    A redirect is returned with an empty body so the other page cannot verify the listing."""
    src = listing_source_url(item)
    fetch = fetch or globals()['fetch']
    if not src:
        return {'ok': False, 'error': 'no source url', 'text': '', 'final_url': '', 'html': ''}
    import robots_check
    rtext, rpath = _robots_text(src)
    if robots_check.blocked(rtext, rpath):  # the site asks us not to read this page: no fetch, hours not guessed
        return {'ok': False, 'error': 'not fetched, robots', 'text': '', 'final_url': '', 'html': '', 'robots': True}
    got = fetch(src) or {}
    if not got.get('ok'):
        return {'ok': False, 'http': got.get('http'), 'error': got.get('error') or 'no response', 'text': '', 'final_url': got.get('final_url') or '', 'html': ''}
    landed = got.get('final_url') or src
    if not discover.source_page_ok(src, landed):
        return {'ok': True, 'http': got.get('http'), 'final_url': landed, 'text': '', 'html': '', 'error': 'redirect'}
    text = text_of(got.get('html') or '')
    if discover.page_has_complete_times(text, item.get('postcode')):
        return {'ok': True, 'http': got.get('http'), 'final_url': landed, 'text': text, 'rendered': False}
    if render:
        rendered = render(src) or {}
        rland = rendered.get('final_url') or ''
        rhtml = rendered.get('html') or ''
        rtext = rendered.get('text') or (text_of(rhtml) if rhtml else '')
        if rtext and discover.source_page_ok(src, rland):
            return {'ok': True, 'http': rendered.get('http') or 200, 'final_url': rland, 'text': rtext, 'rendered': True}
        if rland and not discover.source_page_ok(src, rland):
            return {'ok': True, 'http': rendered.get('http'), 'final_url': rland, 'text': '', 'rendered': True, 'error': 'redirect'}
    return {'ok': True, 'http': got.get('http'), 'final_url': landed, 'text': text, 'rendered': False, 'incomplete': True}
def render_polite(url):
    """Headless render through the same per-host gap as fetch. No saved page."""
    def load(u):
        got = discover.render_live(u) or {}
        if not got.get('ok'):
            return {'ok': False, 'http': got.get('http'), 'error': got.get('error') or 'render failed', 'final_url': got.get('final_url') or u, 'html': ''}
        return {'ok': True, 'http': got.get('http') or 200, 'final_url': got.get('final_url') or u, 'html': got.get('html') or ''}
    return _polite(url, load)
def review_hours(items, state, flag, deadline, fetch=None, render=None):
    """One verdict per listing that shows a source URL. Previous evidence is never copied forward.
    A listing not reached this run is unclear, not still verified."""
    fetch = fetch or globals()['fetch']
    render = render if render is not None else render_polite
    state.setdefault('hours', {})
    n = 0
    for i in items:
        if i.get('type') not in ('foodbank', 'location'): continue
        src = listing_source_url(i)
        if not src: continue
        n += 1
        if time.time() > deadline:
            # Not opened this run. Drop any previous verified quote. The website skip already reports it once;
            # one row per listing would bury the review list.
            state['hours'][i['id']] = {'status': 'unclear', 'evidence': '', 'source_url': src, 'final_url': '',
                                       'note': 'unclear: not checked this run; previous hours are not verified. ' + UNCLEAR_LINE,
                                       'rendered': False, 'checked_at': NOW.isoformat()}
            continue
        verdict = hours_verdict(i, read_source(i, fetch=fetch, render=render))
        state['hours'][i['id']] = {'status': verdict['status'], 'evidence': verdict.get('evidence') or '', 'source_url': src,
                                   'final_url': verdict.get('final_url') or '', 'note': verdict.get('note') or '',
                                   'rendered': bool(verdict.get('rendered')), 'checked_at': NOW.isoformat()}
        if verdict['status'] != 'verified':
            flag(i['id'], 'opening times unclear', name=i.get('name') or '', website=src, id=i['id'],
                 note=verdict.get('note') or '', evidence=verdict.get('evidence') or '')
    return n
SITE_NAMES = {}  # website -> listing names, set by main(); a page must mention a food bank or one of these
def check_site(url, order=None):
    """Fetch with the methods in `order` (plain, then https for an http URL). Stops at the first that works.
    The order comes from per-site method memory so a method that healed this site last time is tried first.
    A robots.txt Disallow skips the fetch. Hours are not guessed, and the place is not removed.
    A sub-page website is read alone (no links followed). Phones also come from the locations/centres page when there is one."""
    text, path = _robots_text(url)
    import robots_check
    if robots_check.blocked(text, path):
        return {'url': url, 'checked_at': NOW.isoformat(), 'ok': False, 'robots': True, 'http': None,
                'error': 'not fetched, robots', 'hours_hash': '', 'phones': [], 'hours_sample': [], 'method': None, 'methods_tried': []}
    order = list(order or (['plain', 'https'] if str(url).startswith('http://') else ['plain']))
    home = {'ok': False, 'http': None, 'error': 'not tried'}; used, tried = None, []
    for m in order:
        if m == 'plain': home = fetch(url)
        elif m == 'https' and str(url).startswith('http://'): home = fetch('https://' + str(url)[7:])
        else: continue
        tried.append(m); used = m
        if home.get('ok'): break
    res = {'url': url, 'checked_at': NOW.isoformat(), 'http': home.get('http'), 'method': used if home.get('ok') else None, 'methods_tried': tried}
    if not home['ok']: res.update(ok=False, error=home.get('error') or 'not tried'); return res
    pages = [(home['final_url'], home['html'])]
    sub = is_subpage(url)
    for u in ([] if sub else links(home['html'], home['final_url'])):
        r = fetch(u)
        if r['ok']: pages.append((r['final_url'], r['html']))
    phone_pages = list(pages)
    for u in ([] if sub else links(home['html'], home['final_url'], phone_pass=True)):
        if u in {p for p, _ in phone_pages} or not re.search(r'locations|centres', u, re.I): continue
        r = fetch(u)
        if r['ok']: phone_pages.append((r['final_url'], r['html']))
    t = '\n'.join(text_of(h) for _, h in pages)
    pt = '\n'.join(text_of(h) for _, h in phone_pages)
    a, ev = access(t)
    hours = sorted({re.sub(r'\s+', ' ', m.group(0)).lower() for m in DAYS.finditer(t)})[:30]
    phones = sorted({p for p in (norm_phone(x) for x in PHONE.findall(pt)) if p and not p.startswith(('0800', '0808', '0300', '0345', '0844', '0845', '0870', '0330')) or p.startswith(('01', '02', '07'))} - {''})
    tel = sorted({p for p in (norm_phone(urllib.parse.unquote(x)) for _, h in phone_pages for x in re.findall(r'href=["\']tel:([^"\']+)', h, re.I)) if p})
    import phone_rule
    context = {p: why for p in phones if (why := phone_rule.other_line_reason(pt, p))}
    res.update(tel=tel[:4], contact_labels=phone_rule.labels_in_text(pt, norm_phone), ok=True, final_url=home['final_url'], pages=[u for u, _ in phone_pages], access=a, access_evidence=ev,
               hours_hash=hashlib.sha1('\n'.join(hours).encode()).hexdigest()[:12] if hours else '', hours_sample=hours[:4],
               seasonal=snippet(t, SEASON), closed=snippet(t, CLOSED), perm_closed=snippet(t, PERM_CLOSED), phones=phones[:8], needs=needs_list(t),
               subpage=sub, fb_mention=phone_rule.mentions_food_bank(pt, SITE_NAMES.get(url) or ()), phone_context=context)
    return res

# ---------- main ----------
def load_data():
    s = open(DATA, encoding='utf-8').read(); return s, json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))

ACC = os.path.join(ROOT, 'access.js')
def load_access():
    try: s = open(ACC, encoding='utf-8').read(); return json.loads(s[s.index('{'):s.rindex('}') + 1])
    except Exception: return {}

def source_errors(sites, results, by_site, when):
    """Point 31 (24 Oct 2026): per-source error log (parse failure, timeout, HTTP error, paused, not reached)."""
    errs = []
    for u in sites:
        r = results.get(u) or {}
        if r.get('ok') is True: continue
        errs.append(dict(website=u, name=(by_site.get(u) or [{}])[0].get('foodbank') or (by_site.get(u) or [{}])[0].get('name'), http=r.get('http'), error=r.get('error') or 'unknown', fail_runs=r.get('fail_runs')))
    return dict(run=when, checked=len(sites), errors=errs)

def site_gap(pins):
    """Share of missing facts for a website's pins (no phone, no own-site opening times): 0 = complete, 1 = nothing."""
    if not pins: return 0.0
    miss = sum((not (i.get('phone') or '').strip()) + (not (i.get('opening_times') or {}).get('status') == 'TIMES_FOUND') for i in pins)
    return round(miss / (2 * len(pins)), 3)

def retry_first(sites, queue):
    """Point 3 (24 Oct 2026): sites that failed or were not reached last run are checked first, so the time budget never starves them."""
    q = set(queue); return [u for u in sites if u in q] + [u for u in sites if u not in q]

def phone_locked(i):
    """Point 1 (Dean, 24 Oct 2026): hand-checked or locked phones are never overwritten automatically."""
    return bool(i.get('phone_checked') or i.get('locked'))

def phone_baseline_path(root=None):
    return os.path.join(root or ROOT, 'overrides', 'phone_baseline.json')

def in_phone_baseline(iid, root=None):
    """True when overrides/phone_baseline.json exists and this id is in it.
    A missing file is not a listing (the auto-apply path treats that separately). An unreadable file locks."""
    root = root or ROOT
    path = phone_baseline_path(root)
    if not os.path.isfile(path): return False
    try:
        import phone_lock
        return bool(phone_lock.is_listed(iid, root))
    except ImportError:
        pass
    try: data = json.load(open(path, encoding='utf-8'))
    except Exception: return True
    return bool(iid) and iid in (data.get('listings') or {})

def listing_phone_frozen(iid, root=None):
    """The clear-phone auto-apply must hold this listing.
    No baseline file yet (PR 211 not merged): every existing listing is locked.
    Once the file exists, only an id recorded in it is locked. A new id may still be applied."""
    if not os.path.isfile(phone_baseline_path(root)): return True
    return in_phone_baseline(iid, root)

def _mark_section(root, filename, tag, line):
    path = os.path.join(root, 'reports', filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    start, end = '<!-- %s -->' % tag, '<!-- /%s -->' % tag
    prev = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if start in prev and end in prev:
        pre, rest = prev.split(start, 1)
        mid, post = rest.split(end, 1)
        if line not in mid: mid = mid.rstrip() + '\n' + line + '\n'
        elif not mid.endswith('\n'): mid += '\n'
        text = pre + start + '\n' + mid.lstrip('\n') + end + post
    else:
        text = prev.rstrip() + '\n\n' + start + '\n' + line + '\n' + end + '\n'
    if not text.endswith('\n'): text += '\n'
    open(path, 'w', encoding='utf-8').write(text)

def hold_phone_for_dean(item, proposed, source, root=None, name=''):
    """Hold one new number for Dean and log its source. The stored phone and tel are not written."""
    root = root or ROOT
    try:
        import phone_lock
    except ImportError:
        phone_lock = None
    if phone_lock is not None:
        phone_lock.hold(root, item.get('id'), 'phone', item.get('phone'), proposed, source or '', 'phone fix', item.get('name') or name or '')
        return
    kept = item.get('phone') if str(item.get('phone') or '').strip() else '(none)'
    shown = proposed if str(proposed or '').strip() else '(blank)'
    line = '- blocked, held for Dean | %s | phone | via phone fix | source %s | stored %s | proposed %s | unchanged (byte-identical)' % (
        item.get('id'), source or '(none)', kept, shown)
    who = item.get('name') or name
    if who: line += ' | ' + who
    for fn in ('pending_dean.md', 'anomaly_brake.md'):
        _mark_section(root, fn, 'phone lock', line)

def record_clear_phones(items, new, source, root=None, name=''):
    """Listings a confirmed single new number may be written onto. Frozen listings are held and left byte-identical."""
    root = root or ROOT
    apply_to = []
    for i in items:
        if listing_phone_frozen(i.get('id'), root):
            hold_phone_for_dean(i, new, source, root, i.get('name') or name)
        else:
            apply_to.append(i)
    return apply_to

def apply_phone_fixes(by_site, fixes, flag, root=None, applied=None, undone=None, centre_phones=None, held=None):
    """Apply auto phone fixes, skipping locked/hand-checked entries; skipped changes go to Dean's review list.
    A listing in the phone baseline is never changed here: the proposal is held for Dean.
    Every stored fix goes through fix_gate_reasons on every run; a fix that fails it is held with its reasons.
    `applied` collects (key, fix) only for numbers that were actually written; `held` collects (key, fix, reasons)."""
    root = root or ROOT
    if undone is None:
        try: undone = json.load(open(os.path.join(root, PHONE_UNDONE), encoding='utf-8'))
        except Exception: undone = {}
    if centre_phones is None:
        import own_locations
        centre_phones = own_locations.load_centre_phones(root)
    everyone = [i for lst in by_site.values() for i in lst]
    site_of = {i.get('id'): u for u, lst in by_site.items() for i in lst}
    n = 0
    for key, f in (fixes or {}).items():
        if not isinstance(f, dict): continue
        if f.get('centre_id'):
            u = site_of.get(f['centre_id'])
            if u is None: continue
            pins = by_site[u]; lst = [i for i in pins if i.get('id') == f['centre_id']]
        else:
            u = key
            if u not in by_site: continue
            pins = lst = by_site[u]
        lst = [i for i in lst if norm_phone(i.get('phone')) == f['old']]
        if not lst: continue
        why = fix_gate_reasons(key, f, pins, fixes, everyone, undone, centre_phones)
        if why:
            for i in lst:
                flag(key + '|' + i.get('id', ''), 'phone fix held (gate)', name=i.get('name', ''), id=i.get('id', ''), website=u, stored=i.get('phone'), proposed=f.get('new'), source=f.get('source', ''), note='; '.join(why))
            if held is not None: held.append((key, f, why))
            continue
        if not f.get('centre_id'): lst = [i for i in lst if _kind(i) == 'foodbank']
        for i in lst:
            if listing_phone_frozen(i.get('id'), root) and (i.get('phone') != f['new'] or i.get('tel') != f['new']):  # no baseline file: every listing is locked
                phone_lock.hold(root, i.get('id'), 'phone', i.get('phone'), f['new'], f.get('source') or '', 'phone fix', i.get('name') or '')
                flag(u + '|' + i.get('id', ''), 'phone change skipped (frozen in phone baseline)', name=i.get('name', ''), id=i.get('id', ''), website=u, stored=i.get('phone'), proposed=f['new'], source=f.get('source', ''), note='not applied: this number is frozen in overrides/phone_baseline.json and held for Dean')
                continue  # phone and tel stay byte-identical
            if phone_locked(i):
                flag(u + '|' + i.get('id', ''), 'phone change skipped (locked / hand-checked)', name=i.get('name', ''), id=i.get('id', ''), website=u, stored=i.get('phone'), proposed=f['new'], source=f.get('source', ''), note='not applied because this phone is marked phone_checked or locked; change it by hand if right')
                continue
            if phone_rule.is_dean(f.get('new')):  # rule 21: Dean's own details are never published
                flag(u + '|' + i.get('id', ''), 'phone held', name=i.get('name', ''), id=i.get('id', ''), website=u, proposed=f.get('new'), source=f.get('source', ''), note=phone_rule.DEAN_REASON)
                continue
            i['phone'] = i['tel'] = f['new']; i['phone_source'] = f['source']
            if f.get('label'): i['phone_label'] = f['label']
            n += 1
            if applied is not None: applied.append((key, f))
    return n

import auto_rules, phone_rule; RULES = auto_rules.load()  # Dean 25 Oct 2026; phone_rule is rule 21
MAY_CLOSED = RULES['closure_card_note']
def apply_closure_notes(items, pending):
    """Dean 25 Oct 08:20: a confirmed own-site closure keeps its pin; the card says it may have closed (every run, so build.py rebuilds can't drop it)."""
    for i in items:
        if i['id'] in pending: i['notice'] = MAY_CLOSED
TIMES_LOG = 'reports/times_auto_applied.json'
def gate_applied_times(root=None):
    """Times the refresh gate (discover.times_gate_apply, run by build.py before this script) newly applied this run:
    entries in reports/times_auto_applied.json that the last published commit does not have. They count towards the brake."""
    import subprocess
    root = root or ROOT
    try: now = json.load(open(os.path.join(root, TIMES_LOG), encoding='utf-8'))
    except Exception: return []
    try:
        head = json.loads(subprocess.run(['git', 'show', 'HEAD:' + TIMES_LOG], cwd=root, capture_output=True, text=True, check=True).stdout)
    except Exception:
        print('anomaly brake: no published copy of %s to compare with; refresh-gate times not counted' % TIMES_LOG); return []
    published = {json.dumps(e, sort_keys=True) for e in head if isinstance(e, dict)}
    return [e for e in now if isinstance(e, dict) and e.get('path') == 'cross_check' and not e.get('reverted')
            and json.dumps(e, sort_keys=True) not in published]
def signal_brake(stop):
    """Step output read by refresh.yml: brake=stop fails the 'Anomaly brake' step, so the commit step never runs."""
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a', encoding='utf-8') as fh: fh.write('brake=%s\n' % ('stop' if stop else 'ok'))
def write_pending_closures(pending):
    """Closure section of reports/pending_dean.md (kept between markers; publish_gate.py preserves it)."""
    pd = os.path.join(REP, 'pending_dean.md'); t = open(pd, encoding='utf-8').read() if os.path.exists(pd) else ''
    t = re.sub(r'(?s)\n*<!-- closures -->.*?<!-- /closures -->\n?', '', t)
    L = ['<!-- closures -->', '## Possible closures - still on the map with "May have closed" note (%d)' % len(pending), '',
         'To remove one, add its id to overrides/foodbank_closed.json; to clear the note, delete it from reports/closures_pending.json.', '']
    L += ['- %s (%s) - %s - %s, since %s' % (v.get('name'), k, v.get('evidence'), v.get('url') or v.get('website'), v.get('since')) for k, v in sorted(pending.items())] or ['- none']
    open(pd, 'w', encoding='utf-8').write(t.rstrip() + '\n\n' + '\n'.join(L + ['<!-- /closures -->']) + '\n')

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
    # Removals Dean approved / confirmed by hand (overrides/foodbank_closed.json, e.g. Welshpool 25 Oct 08:57) always stay off,
    # whichever build step let them back in, and never sit on the 'may have closed' list.
    approved_off = {k for k in closed_raw if not k.startswith('_')}
    remove |= {i['id'] for i in items if i['id'] in approved_off}
    for x, t in tags.items():
        if x in acc: acc[x] = t['tag']   # build_access.py regenerated access.js from the CSVs; re-apply our flips
    fixes = rj('phone_fixes.json', {})      # website -> {"old", "new", "since", "source"}
    try: undone = json.load(open(os.path.join(ROOT, PHONE_UNDONE), encoding='utf-8'))
    except Exception: undone = {}
    fixes = {u: f for u, f in fixes.items() if undone.get(u) != f.get('new')}  # an undone fix is never re-applied
    fixes = {u: f for u, f in fixes.items() if norm_phone(f.get('new')) not in undone_numbers(undone, u)}  # every number Dean undid, not just the last
    import own_locations
    centre_phones = own_locations.load_centre_phones(ROOT)  # pin id -> that centre block's own line (own_locations.py)
    changes = rj('access_changes.json', [])
    review = rj('daily_review.json', {})
    today = review.get(DAY, {'date': DAY, 'runs': [], 'items': {}}); review = {k: v for k, v in review.items() if k >= (NOW.date() - datetime.timedelta(days=14)).isoformat()}
    flag = lambda key, cat, **kw: today['items'].__setitem__(cat + '|' + key, dict(category=cat, first_flagged=today['items'].get(cat + '|' + key, {}).get('first_flagged', NOW.isoformat()), **kw))
    by_site = {}; by_id = {i['id']: i for i in items}
    for i in items:
        w = (i.get('website') or '').strip()
        if w.startswith('http'): by_site.setdefault(w, []).append(i)
    for u in by_site: SITE_NAMES[u] = sorted({x for i in by_site[u] for x in (i.get('name'), i.get('foodbank')) if x})
    # Dean 25 Oct 08:01: self-learning order (scripts/learning.py) - weekly floor first, then high-yield / gap-heavy sites;
    # sites failing repeatedly rest (back-off, never past the weekly floor). Only the ORDER/selection changes, never the rules below.
    LS = learning.load(); gaps = {u: site_gap(by_site[u]) for u in by_site}
    import learning_signals  # corrections, change signals, source trust, season, demand, visitor reports (last run's file)
    order, resting_sites, _ = learning.plan(LS, sorted(by_site), DAY, gaps, boosts=learning_signals.boosts())
    conflicted = {c.get('website') for c in (learning_signals.rj('reports/learning_signals.json', {}).get('conflicts') or []) if isinstance(c, dict) and c.get('website')}
    sites = retry_first(order, [u for u in (state.get('retry_queue') or []) if u not in resting_sites])  # point 3: last run's failed/unchecked sites go first
    if os.environ.get('SAMPLE'): sites = [u for u in sites if u.startswith('https') and 'foodbank.org.uk' not in u][:int(os.environ['SAMPLE'])]
    closure_pending = {k: v for k, v in rj('closures_pending.json', {}).items() if k not in approved_off}  # id -> evidence; Dean decides (25 Oct 08:20)
    log = []  # must exist before the new/removed block below (bug since 22 Oct: UnboundLocalError)
    this_run = []  # rows inserted into access_changes this run; the brake counts only the applied ones
    prov = []  # why an automatic edit was allowed; written only when one is actually applied
    # (3) new / removed food banks vs last run
    ids = sorted(i['id'] for i in items if i['type'] == 'foodbank'); prev_ids = set(state.get('ids') or [])
    if prev_ids:
        for x in sorted(set(ids) - prev_ids):
            i = next(j for j in items if j['id'] == x)
            e = dict(when=NOW.isoformat(), id=x, website=i.get('website') or '', name=i['name'], kind='new food bank', old='not on map', new='added (%s)' % (i.get('postcode') or ''), source=(i.get('own_site_check') or {}).get('final_url') or i.get('website') or i.get('givefood') or '')
            changes.insert(0, e); log.append(e); this_run.append(e)  # held for Dean: logged, not an applied change
        for x in sorted(prev_ids - set(ids)):
            e = dict(when=NOW.isoformat(), id=x, website='', name=x, kind='removed', old='on map', new='gone (no longer in the feed / closed on own site / excluded)', source='logs/foodbank_closed.json'); changes.insert(0, e); log.append(e); this_run.append(e)
    # fetch everything (time-boxed; whatever is left is reported, not guessed)
    t0 = time.time(); results = {}
    def job(u):
        if time.time() - t0 > BUDGET: return u, {'url': u, 'ok': None, 'error': 'time budget reached - not checked this run'}
        try:
            avail = ['plain', 'https'] if u.startswith('http://') else ['plain']
            order = learning.method_order(LS, u, avail)
            try: return u, check_site(u, order)
            except TypeError: return u, check_site(u)  # a one-argument stand-in (tests) still works
        except Exception as e: return u, {'url': u, 'ok': False, 'error': 'check error: %r' % e}
    with cf.ThreadPoolExecutor(12) as ex:
        for u, r in ex.map(job, sites): results[u] = r
    stats = dict(sites=len(sites), ok=0, failed=0, skipped=0, voucher=0, walkin=0, mixed=0, unclear=0, flips=0, phone_fixes=0, closures=0)
    for u in sites:
        r, prev = results[u], state['sites'].get(u, {}); names = sorted({i['foodbank'] for i in by_site[u]}); name = names[0]
        if r.get('ok') is None:
            stats['skipped'] += 1
            # Not reached this run. Access and phones stay so a 2-run confirmation can still complete next time.
            # Opening times do not: the previous hash is not a live reading and is not left verified.
            kept = {k: prev.get(k) for k in ('access', 'needs', 'phones', 'closed', 'fail_runs')}
            drop_saved_hours(kept)
            kept.update(checked_at=NOW.isoformat(), error=r.get('error'), http=None)
            state['sites'][u] = kept
            flag(u, 'opening times not read', name=name, website=u, error=r.get('error'), note='not checked this run; previous hours are not verified. ' + UNCLEAR_LINE)
            continue
        if r.get('robots'):
            stats['robots'] = stats.get('robots', 0) + 1; r['fail_runs'] = prev.get('fail_runs', 0)
            flag(u, 'not fetched, robots', name=name, website=u, note='the site asks us not to read this page. Opening hours were not guessed. The place stays on the map.')
            state['sites'][u] = {k: r.get(k) for k in ('checked_at', 'http', 'error', 'robots', 'fail_runs')}; continue
        if not r['ok']:
            stats['failed'] += 1; r['fail_runs'] = prev.get('fail_runs', 0) + 1
            for k in ('access', 'needs', 'phones', 'closed'): r[k] = prev.get(k)
            drop_saved_hours(r)  # Rule 27: a failed live open is not a times check
            r['perm_closed'] = None  # a failed fetch never confirms a closure
            flag(u, 'opening times not read', name=name, website=u, error=r.get('error'), note='live page did not open; no saved copy used. ' + UNCLEAR_LINE)
            if r['fail_runs'] >= 2: flag(u, 'dead or unreachable website', name=name, website=u, error=r['error'], failed_runs=r['fail_runs'], phone=by_site[u][0].get('phone'), note='site failed %d runs in a row - check contact details' % r['fail_runs'])
            state['sites'][u] = {k: r.get(k) for k in ('checked_at', 'http', 'error', 'access', 'hours_hash', 'hours_sample', 'hours_status', 'hours_evidence', 'needs', 'phones', 'seasonal', 'closed', 'perm_closed', 'fail_runs')}; continue
        stats['ok'] += 1; r['fail_runs'] = 0; stats[r['access']] += 1
        got = (1 if r.get('hours_hash') else 0) + len(r.get('phones') or [])
        had = ((1 if prev.get('hours_hash') else 0) + len(prev.get('phones') or [])) if prev.get('checked_at') else None
        r['empty_parse'] = bool(learning.empty_parse(r.get('http'), got, had))
        # (1) access - per pin, against access.js (hand-read CSVs + earlier auto flips). A flip needs the
        # same clear own-site result on 2 runs in a row; unclear never changes anything (= walk-ins welcome).
        curs = {i['id']: acc.get(i['id'], 'unconfirmed') for i in by_site[u] if i['id'] in acc}
        if r['access'] in ('voucher', 'walkin'):
            todo = [x for x, c in curs.items() if c != r['access']]
            trus = [x for x in todo if r['access'] == 'walkin' and by_id[x].get('network') == 'Trussell']
            if trus:  # Trussell = voucher (Dean); walk-in wording on a Trussell site is a flag, never an automatic flip
                flag(u, 'Trussell site with walk-in wording', name=name, website=u, current_tag='voucher', evidence=r['access_evidence'], note='left as voucher - please check')
                todo = [x for x in todo if x not in trus]
            if todo and prev.get('access') == r['access'] and not learning.allow_under_rules('voucher/walk-in flips', RULES, learning.confidence_for(u, conflicted)):
                flag(u, 'access flip held (confidence under the rules)', name=name, website=u, current_tag=', '.join(sorted(set(curs[x] for x in todo))), evidence=r['access_evidence'], note='the auto-apply rules would allow this, but confidence is too low - left for you')
            elif todo and prev.get('access') == r['access']:
                for x in todo:
                    entry = dict(when=NOW.isoformat(), id=x, website=u, name=name, old=curs[x], new=r['access'], evidence=r['access_evidence'], source=r['final_url'])
                    changes.insert(0, entry); this_run.append(entry); tags[x] = dict(tag=r['access'], since=DAY, evidence=r['access_evidence'], source=r['final_url'], was=curs[x]); acc[x] = r['access']
                today['items'].pop('access flip pending (confirms next run)|' + u, None)
                log.append(dict(name=name, website=u, old=', '.join(sorted(set(curs[x] for x in todo))), new=r['access'] + ' (%d pins)' % len(todo), source=r['final_url'])); stats['flips'] += len(todo)
                note = learning.provenance('voucher/walk-in flips', learning.confidence_for(u, conflicted) if hasattr(learning, "confidence_for") else None, r.get('final_url'), RULES)
                if note: prov.append(dict(note, when=NOW.isoformat()))
            elif todo:
                flag(u, 'access flip pending (confirms next run)', name=name, website=u, current_tag=', '.join(sorted(set(curs[x] for x in todo))), evidence=r['access_evidence'], note='clear %s wording found; applied automatically if seen again next run' % r['access'])
        elif r['access'] == 'mixed':
            flag(u, 'access mixed', name=name, website=u, current_tag=', '.join(sorted(set(curs.values()))) or 'unconfirmed', evidence=r['access_evidence'], note='site mentions both voucher and walk-in - left as is, please decide')
        elif 'voucher' in curs.values() and prev.get('access') == 'voucher':
            flag(u, 'access now uncertain', name=name, website=u, current_tag='voucher', note='voucher wording no longer found - tag kept until you decide')
        # (2) hours. A hash of day-shaped text is not a check of the listing. The listing check is review_hours,
        # against the source URL on the card. A seasonal notice on the site is still reported.
        if r['seasonal'] and r['seasonal'] != prev.get('seasonal'): flag(u, 'seasonal/holiday hours notice', name=name, website=u, text=r['seasonal'])
        # (3) closure: clear permanent wording on 2 runs in a row. Dean 25 Oct 08:20: NEVER removed automatically -
        # the pin stays with the card note MAY_CLOSED and goes to Dean's pending list (reports/closures_pending.json -> pending_dean.md).
        if r['perm_closed'] and prev.get('perm_closed'):
            ids_ = [i['id'] for i in by_site[u] if i['id'] not in closed_hold]
            for x in ids_:
                if learning.allow_under_rules('remove_place', RULES, learning.confidence_for(u, conflicted)): closed_ov[x] = dict(url=r['final_url'], evidence=r['perm_closed'], confirmed='auto %s' % DAY); remove.add(x)
                if x not in closure_pending:
                    closure_pending[x] = dict(name=name, website=u, url=r['final_url'], evidence=r['perm_closed'], since=DAY)
                    e = dict(when=NOW.isoformat(), id=x, website=u, name=name, kind='closure', old='on map', new='kept on map with "May have closed" note - waiting for your OK', source=r['final_url'], evidence=r['perm_closed'])
                    changes.insert(0, e); log.append(e); this_run.append(e); stats['closures'] += 1  # note waits for Dean; the pin is not removed
            today['items'].pop('closure pending (confirms next run)|' + u, None)
            if len(ids_) < len(by_site[u]): flag(u, 'closure on hold (your hold list)', name=name, website=u, text=r['perm_closed'])
        elif r['perm_closed']: flag(u, 'closure pending (confirms next run)', name=name, website=u, text=r['perm_closed'], note='if the wording is still there next run the card gets a "May have closed" note and it goes to your pending list (never removed automatically)')
        elif r['closed'] and r['closed'] != prev.get('closed'): flag(u, 'own site mentions closure (temporary/unclear)', name=name, website=u, text=r['closed'])
        # (4) phones
        stored = {norm_phone(i.get('phone')) for i in by_site[u]} - {''}
        if own_site_misses_stored(stored, r['phones']):
            clear = len(r['phones']) == 1 and r.get('tel') == r['phones'] and prev.get('phones') == r['phones'] and u not in fixes
            gate = phone_gate_reasons(u, r, prev, undone) if clear else []
            if clear and not learning.allow_under_rules('clear single new phone on own site', RULES, learning.confidence_for(u, conflicted)):
                flag(u, 'phone fix held (confidence under the rules)', name=name, website=u, stored=sorted(stored), on_site=r['phones'], note='the auto-apply rules would allow a single confirmed number, but confidence is too low - left for you')
            elif clear and gate:
                flag(u, 'phone fix held (strict gate)', name=name, website=u, stored=sorted(stored), on_site=r['phones'], source=r.get('final_url') or '', note='; '.join(gate))
            elif clear:
                new = r['phones'][0]
                lab = (r.get('contact_labels') or {}).get(new, '')
                targets, why = site_phone_plan(by_site[u], new, centre_phones)
                doubt = (r.get('phone_context') or {}).get(new) or ('' if r.get('fb_mention') is not False else 'the page does not mention a food bank or the listing name')
                d = phone_rule.decide(dict(phone=new, own_page=own_host(u, r.get('final_url')), verified=not gate and bool(targets), label=lab,
                                           doubtful=bool(why or doubt), reason=why or doubt))
                if d['action'] == 'show':
                    old = norm_phone(targets[0].get('phone'))
                    listed = [i for i in targets if listing_phone_frozen(i.get('id'), ROOT)]
                    for i in listed:  # baselined listings (or every listing, with no baseline file) are held, not auto-applied
                        hold_phone_for_dean(i, new, r.get('final_url') or '', ROOT, name)
                    if len(listed) < len(targets):
                        fixes[u] = dict(old=old, new=new, since=DAY, source=r['final_url'], label=d['label'], pin=targets[0].get('id'), fb_mention=r.get('fb_mention') is not False,
                                        first_run_at=prev.get('checked_at'), second_run_at=r.get('checked_at')); stats['phone_fixes'] += 1
                        today['items'].pop('phone number not on own site|' + u, None)
                        e = dict(when=NOW.isoformat(), website=u, name=name, kind='phone', old=old, new=new, source=r['final_url']); changes.insert(0, e); log.append(e); this_run.append(e)
                else:
                    flag(u, 'phone held', name=name, website=u, stored=sorted(stored), on_site=r['phones'], note=d['reason'])
            elif u not in fixes:
                flag(u, 'phone number not on own site', name=name, website=u, stored=sorted(stored), on_site=r['phones'], note='only a single clickable number seen on 2 runs is auto-applied; this one is not clear')
        # (5) items needed
        if r['needs'] and prev.get('checked_at') and r['needs'] != prev.get('needs'): flag(u, 'items-needed list ' + ('updated' if prev.get('needs') else 'published'), name=name, website=u, list=r['needs'])
        state['sites'][u] = {k: r.get(k) for k in ('checked_at', 'http', 'final_url', 'access', 'hours_hash', 'hours_sample', 'hours_status', 'hours_evidence', 'seasonal', 'closed', 'perm_closed', 'phones', 'tel', 'needs', 'fail_runs', 'empty_parse')}
    # (4b) location pins: only their own centre block on the organisation's locations page (own_locations.py), matched by postcode
    for i in items:
        if _kind(i) != 'location' or i['id'] not in centre_phones or i['id'] in fixes: continue
        new, why = centre_phone_plan(i, centre_phones[i['id']])
        src = centre_phones[i['id']].get('source_url') or ''
        if why: flag(i['id'], 'centre phone held', name=i.get('name') or '', id=i['id'], website=src, stored=i.get('phone'), proposed=centre_phones[i['id']].get('phone'), note=why)
        elif new:
            fixes[i['id']] = dict(old=norm_phone(i.get('phone')), new=new, since=DAY, source=src, label='', centre_id=i['id'], fb_mention=True,
                                  first_run_at=centre_phones[i['id']].get('prev_run_at'), second_run_at=centre_phones[i['id']].get('run_at'))
            e = dict(when=NOW.isoformat(), website=src, id=i['id'], name=i.get('name') or '', kind='phone', old=norm_phone(i.get('phone')), new=new, source=src)
            changes.insert(0, e); log.append(e); this_run.append(e); stats['phone_fixes'] += 1
    review_hours(items, state, flag, t0 + BUDGET)
    if not os.environ.get('SAMPLE'): state['ids'] = ids
    state['last_run'] = NOW.isoformat()
    wj('source_errors.json', source_errors(sites, results, by_site, NOW.isoformat()))  # point 31: every failed/timed-out source this run, for the digest
    state['retry_queue'] = sorted(u for u in sites if results[u].get('ok') is not True)  # failed or not reached: retried first next run
    found = {e.get('website') for e in log} | {v.get('website') for v in today['items'].values() if v.get('first_flagged', '') >= NOW.isoformat()}
    for u in sites:
        r = results[u]; learning.note_heal(LS, u, r.get('methods_tried') or [], r.get('method'), DAY)
        # a robots block is a completed permission check, not a failed fetch and not a dead link
        checked = True if r.get('robots') else r.get('ok')
        learning.record(LS, u, DAY, checked, finds=int(u in found), method=('robots' if r.get('robots') else (r.get('method') or ((r.get('methods_tried') or [None])[-1]) or 'own_site')), changed=u in {e.get('website') for e in log}, kind='foodbank_site')
    n_own = learning.applied_count(this_run)  # new places held for Dean are in this_run and do not count
    n_times = len(gate_applied_times(ROOT))
    n_applied = n_own + n_times
    brake = learning.anomaly_brake(LS.get('change_counts') or [], n_applied)
    if not brake['stop'] and not os.environ.get('SAMPLE') and not os.environ.get('DRY_RUN'):
        LS.setdefault('change_counts', []); LS['change_counts'] = (LS['change_counts'] + [{'day': DAY, 'changes': n_applied}])[-30:]
    elif brake['stop']:
        LS['anomaly'] = dict(brake, day=DAY)
    if not os.environ.get('SAMPLE') and not os.environ.get('DRY_RUN'):
        learning.prune(LS, DAY, sites)
        learning.snapshot(LS, DAY); learning.save(LS)
        try:
            import replay
            replay.write(replay.cases_from_state(state), os.path.join(REP, 'replay_cases.json'))
        except Exception: pass
    if brake['stop']:
        os.makedirs(REP, exist_ok=True)
        open(os.path.join(REP, 'anomaly_brake.md'), 'w', encoding='utf-8').write(
            '# Stopped\n\n%s\n\nCounted: %d own-site changes (access flips, phone fixes, removals) and %d opening-times changes the refresh gate applied.\n\n'
            'Nothing from this run was published: the refresh workflow fails at its anomaly brake step, before the commit step, '
            'so this run\'s data.js, access tags, phone fixes and times stay off the live site.\n' % (brake['reason'], n_own, n_times))
        signal_brake(True)
        today['runs'].append(dict(at=NOW.isoformat(), **stats)); review[DAY] = today; write_md(today, log, stats)
        print('ANOMALY BRAKE:', brake['reason']); return
    signal_brake(False)
    # apply phone fixes to data.js (every run, since build.py rebuilds from the feed)
    applied_phones = []
    apply_phone_fixes(by_site, fixes, flag, ROOT, applied=applied_phones)
    if not os.environ.get('SAMPLE') and not os.environ.get('DRY_RUN'): log_phone_changes(applied_phones)
    for u, f in applied_phones:
        # PR 204 owns confidence_for and the decision to hold a phone. This log only records a number that was written.
        if hasattr(learning, "confidence_for"): confidence = learning.confidence_for(u, conflicted)
        else: confidence = 0.0 if u in conflicted else None
        note = learning.provenance('clear single new phone on own site', confidence, f.get('source'), RULES)
        if note: prov.append(dict(note, when=NOW.isoformat()))
    if prov:
        prev_p = rj('provenance.json', [])
        if not isinstance(prev_p, list): prev_p = []
        wj('provenance.json', (prev_p + prov)[-200:])
    today['runs'].append(dict(at=NOW.isoformat(), **stats)); review[DAY] = today
    wj('full_check_state.json', state); wj('access_tags.json', tags); wj('phone_fixes.json', fixes); wj('access_changes.json', changes[:2000]); wj('daily_review.json', review)
    write_md(today, log, stats)
    try:
        import rate_ledger
        if rate_ledger.LEDGER.counts and not os.environ.get('SAMPLE') and not os.environ.get('DRY_RUN'): rate_ledger.save(day=DAY)
    except Exception: pass
    print('full check:', json.dumps(stats))
    apply_closure_notes(items, closure_pending); wj('closures_pending.json', closure_pending); write_pending_closures(closure_pending)
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
         'Generated by scripts/full_check.py on every refresh run. Auto-applied (Dean, 25 Oct 2026 rules, overrides/auto_apply_rules.json): clear access flips and clear phone fixes (same result on 2 runs), logged below and in reports/access_changes.json. Confirmed closures stay on the map with a \'May have closed\' note and new food banks are held - both wait for Dean in reports/pending_dean.md. Uncertain or mixed cases are listed for Dean.', '',
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
    path = os.path.join(REP, 'daily_review.md'); extra = ''
    if os.path.exists(path):
        prev = open(path, encoding='utf-8').read()
        m = re.search(r'(?s)<!-- phone lock new -->.*?<!-- /phone lock new -->', prev)
        if m: extra = '\n' + m.group(0) + '\n'
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n' + extra)

if __name__ == '__main__': main()
