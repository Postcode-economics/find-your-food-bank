"""Self-learning, part 2 (Dean, 25 Oct 2026; agreed order: corrections, change signals, source trust, seasonal timing,
demand, weekly self-review, discovery last). Runs after full_check.py in every food bank refresh; writes
reports/learning_signals.json (+ reports/learning_review.md) which the NEXT run uses to order checks.

Hard limits (unchanged from learning.py): this only changes the ORDER and FREQUENCY of checks. It never edits map data,
never adds or removes a place (new places always go to reports/pending_dean.md for Dean's OK), and never invents data:
every number comes from files already in the repo, and an input that does not exist yet (visitor demand, visitor
reports, email bounces) is reported as 'no data yet' and has no effect.

Inputs (all real, all optional):
  corrections   overrides/phones.json, overrides/foodbank_notices.json, manual entries in
                overrides/foodbank_closed.json  (hand fixes by Dean = the feed was wrong for that place)
  agreement     reports/full_check_state.json: stored phone vs the phones on the food bank's own site
  change        reports/full_check_state.json (dead link: fail_runs>=2; 'closed' wording), logs/fb_page_check.json
  signals       (status != ok), overrides/email_bounces.json (ids whose contact email bounced; added by hand)
  seasonal      logs/entry_history.json: real changes (times/phone/closure) per ISO week of year
  demand        reports/demand.json {area or id: visits} exported from our own analytics (optional; none yet)
  visitor       overrides/visitor_reports.json {id: [{when, what}]} from 'Report a mistake' emails (optional)
  crawl timing  reports/full_check_state.json per-host failures + learning_state host latency
"""
import datetime, json, math, os, re, sys, collections, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learning, auto_rules
RULES = auto_rules.load()
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'reports', 'learning_signals.json'); MD = os.path.join(ROOT, 'reports', 'learning_review.md')
# bounded weights (weekly self-review may move each by at most STEP per week, never outside [LO, HI] x default)
DEFAULT_W = {'correction': 0.5, 'signal': 0.8, 'trust': 0.4, 'season': 0.3, 'demand': 0.3, 'visitor': 0.8, 'rhythm': 0.4, 'dean': 0.4, 'problem': 0.8, 'stale_area': 0.4, 'forecast': 0.4, 'conflict': 0.5, 'weather': 0.6, 'empty_parse': 0.5}
COLD_WORDS = ('snow', 'ice', 'cold', 'freezing', 'frost', 'blizzard')
STEP, LO, HI = 0.10, 0.5, 1.5
REAL = ('phone', 'tel', 'opening_times', 'hours', 'access', 'closed', 'removed', 'notice')

def rj(p, d):
    try: return json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
    except Exception: return d
def items_of(p):
    try:
        t = open(os.path.join(ROOT, p), encoding='utf-8').read(); return json.loads(t[t.index('{'):t.rindex('}') + 1])['items']
    except Exception: return []
def source_of(i): return 'IFAN' if i['id'].startswith('ifan-') else ('Give Food' if i.get('givefood') else (i.get('source') or 'other'))
def host(u): return urllib.parse.urlparse(u or '').netloc.lower().removeprefix('www.')
def norm(p): return re.sub(r'\D', '', str(p or '')).replace('44', '0', 1) if str(p or '').startswith('+44') else re.sub(r'\D', '', str(p or ''))

def corrections(items):
    """Hand fixes per place; a source's correction rate lowers trust in it and lifts similar places (same source + host)."""
    ids = set()
    for f in ('overrides/phones.json', 'overrides/foodbank_notices.json'):  # hand fixes only (opening_times.json is mostly automated)
        ids |= {k for k in rj(f, {}) if not k.startswith('_')}
    ids |= {k for k, v in rj('overrides/foodbank_closed.json', {}).items() if not k.startswith('_') and 'auto' not in str(v.get('confirmed', ''))[:5]}
    by = {i['id']: i for i in items}; per = collections.Counter(); tot = collections.Counter(source_of(i) for i in items)
    for x in ids:
        if x in by: per[source_of(by[x])] += 1
    return ids, {s: round(per[s] / tot[s], 4) for s in tot}

def source_blame(items):
    """Which source the hand fix had to correct, by field. The same files as corrections().
    This records the blame. It does not pick a replacement value."""
    by = {i['id']: i for i in items}; blame = collections.defaultdict(lambda: collections.Counter())
    def add(ids, field):
        for x in ids:
            it = by.get(x)
            if it: blame[source_of(it)][field] += 1
    add({k for k in rj('overrides/phones.json', {}) if not str(k).startswith('_')}, 'phone')
    add({k for k in rj('overrides/foodbank_notices.json', {}) if not str(k).startswith('_')}, 'notice')
    add({k for k, v in rj('overrides/foodbank_closed.json', {}).items() if not str(k).startswith('_') and isinstance(v, dict) and 'auto' not in str(v.get('confirmed', ''))[:5]}, 'closure')
    return {s: dict(c) for s, c in blame.items() if c}

def agreement(items, state):
    """Cross-source agreement: is the stored phone one of the phones on the place's own site? Beta(1,1) per source."""
    ok, n = collections.Counter(), collections.Counter(); per_site = {}
    for i in items:
        s = state.get('sites', {}).get((i.get('website') or '').strip()); p = norm(i.get('tel') or i.get('phone'))
        if not s or not p or not s.get('phones') or s.get('fail_runs'): continue
        hit = p in {norm(x) for x in s['phones']}; src = source_of(i); n[src] += 1; ok[src] += hit; per_site[i['website'].strip()] = hit
    return {s: round((ok[s] + 1) / (n[s] + 2), 4) for s in n}, {s: n[s] for s in n}, per_site

def conflicts(items, state):
    """Stored phone vs the phones on the place's own site. Disagreement is flagged for Dean.
    chosen is always None: this never picks a winner and never writes a phone."""
    rows = []
    for i in items:
        u = (i.get('website') or '').strip()
        s = (state.get('sites') or {}).get(u)
        if not u or not s or s.get('fail_runs'): continue
        stored = norm(i.get('tel') or i.get('phone'))
        found = sorted({norm(x) for x in (s.get('phones') or []) if norm(x)})
        if stored and found and stored not in set(found):
            rows.append({'id': i['id'], 'name': i.get('name'), 'website': u, 'field': 'phone',
                         'values': {'stored': stored, 'own_site': found}, 'chosen': None, 'action': 'flag_for_dean'})
    return rows

def change_signals(items, state):
    """Places with a sign that something is changing: dead link, 'closed' wording, FB page gone/renamed, bounced email."""
    sig = collections.defaultdict(list)
    for u, s in state.get('sites', {}).items():
        if (s.get('fail_runs') or 0) >= 2: sig[u].append('dead link (%d runs)' % s['fail_runs'])
        if s.get('closed') or s.get('perm_closed'): sig[u].append('closure wording on own site')
    by = {i['id']: (i.get('website') or '').strip() for i in items}
    for k, v in rj('logs/fb_page_check.json', {}).get('pages', {}).items():
        if v.get('status') not in (None, 'ok') and by.get(k): sig[by[k]].append('Facebook page: ' + str(v.get('status')))
    for k in rj('overrides/email_bounces.json', {}):
        if not k.startswith('_') and by.get(k): sig[by[k]].append('contact email bounced')
    return dict(sig)

def seasonal(today):
    """Real changes per ISO week (from entry_history). A week with more than average changes gets a boost, scaled 0..1."""
    wk = collections.Counter(); years = set()
    for v in rj('logs/entry_history.json', {}).values():
        for c in v:
            if c.get('change') not in REAL and c.get('change') not in ('added', 'removed'): continue
            o, n = c.get('old'), c.get('new')
            if isinstance(o, dict) and isinstance(n, dict) and {k: o.get(k) for k in ('raw', 'structured')} == {k: n.get(k) for k in ('raw', 'structured')}: continue  # date-only refresh, not a change
            try: d = datetime.date.fromisoformat(c['when'][:10])
            except Exception: continue
            wk[d.isocalendar()[1]] += 1; years.add(d.year)
    w = today.isocalendar()[1]; nxt = [(w + k - 1) % 53 + 1 for k in (0, 1)]
    if not wk: return 0.0, dict(wk), 'no history yet'
    avg = sum(wk.values()) / max(len(wk), 1); cur = max(wk.get(x, 0) for x in nxt)
    return round(max(0.0, min((cur / avg) - 1, 1.0)) if avg else 0.0, 3), dict(sorted(wk.items())), '%d weeks of history (%s)' % (len(wk), ', '.join(map(str, sorted(years))))

def demand(items):
    d = rj('reports/demand.json', None)
    if not d: return {}, 'no visitor data yet (reports/demand.json not present) - no effect'
    mx = max(d.values()) or 1; out = {}
    for i in items:
        v = d.get(i['id']) or d.get(i.get('district') or '') or 0
        if v and i.get('website'): out[i['website'].strip()] = round(math.log1p(v) / math.log1p(mx), 3)
    return out, 'from reports/demand.json (%d areas/places)' % len(d)

def dean_effect(kind):
    """What learning from Dean's past decisions is allowed to do.
    He is asked every time. The only things kept are queue priority and his wording. Nothing is published."""
    return {'ask': True, 'learns': 'priority_or_wording', 'publishes': False, 'kind': kind}

def dean_learning(items):
    """Hand decisions (phones, notices, manual closures, places he has already OK'd).
    Same-host places move up the queue. His wording is remembered and never copied onto another place.
    A past yes is not a yes for the next place."""
    phones = {k: v for k, v in rj('overrides/phones.json', {}).items() if not str(k).startswith('_')}
    notices = {k: v for k, v in rj('overrides/foodbank_notices.json', {}).items() if not str(k).startswith('_')}
    closed = {k for k, v in rj('overrides/foodbank_closed.json', {}).items()
              if not str(k).startswith('_') and isinstance(v, dict) and 'auto' not in str(v.get('confirmed', ''))[:5]}
    approved = {k for k in rj('overrides/foodbank_approved_new.json', {}) if not str(k).startswith('_')}
    approved |= {k for k in rj('overrides/foodbank_added.json', {}) if not str(k).startswith('_')}
    for layer, ids in rj('overrides/approved_new_places.json', {}).items():
        if str(layer).startswith('_') or not isinstance(ids, dict): continue
        approved |= set(ids)
    by = {i['id']: i for i in items}; wording = {}; hosts = set()
    for pid, text in phones.items():
        if isinstance(text, str) and text.strip():
            wording[pid] = {'field': 'phone', 'text': text.strip(), 'from': 'overrides/phones.json'}
    for pid, v in notices.items():
        if isinstance(v, dict) and (v.get('notice') or '').strip():
            wording[pid] = {'field': 'notice', 'text': v['notice'].strip(), 'from': 'overrides/foodbank_notices.json'}
    for pid in set(phones) | set(notices) | closed | approved:
        it = by.get(pid)
        if not it: continue
        h = host(it.get('website'))
        if h: hosts.add(h)
    sites = {(i.get('website') or '').strip() for i in items if host(i.get('website')) in hosts}
    sites.discard('')
    note = 'remembers priority and wording only; Dean is still asked every time (%d sites)' % len(sites) if sites else 'no hand decisions to learn from yet - no effect'
    return sites, wording, note

def visitor(items):
    v = {k: x for k, x in rj('overrides/visitor_reports.json', {}).items() if not k.startswith('_')}
    by = {i['id']: (i.get('website') or '').strip() for i in items}
    return {by[k]: len(x) for k, x in v.items() if by.get(k)}, ('%d places reported by visitors' % len(v)) if v else 'no visitor reports recorded yet - no effect'

def problem_reports(items):
    """Report a problem submissions (overrides/problem_reports.json), added by hand from the form emails.
    Shape: {listing id: [{when, what}]}. The form itself only sends email, so a missing file has no effect.
    Submissions raise that place's check priority. They do not change the listing."""
    raw = rj('overrides/problem_reports.json', None)
    if not raw: return {}, 'no Report a problem submissions on file (overrides/problem_reports.json) - no effect'
    rows = {k: v for k, v in raw.items() if not str(k).startswith('_') and v}
    by = {i['id']: (i.get('website') or '').strip() for i in items}; out = {}
    for k, v in rows.items():
        u = by.get(k)
        if not u: continue
        out[u] = out.get(u, 0) + (len(v) if isinstance(v, list) else 1)
    return out, ('%d Report a problem submissions' % sum(out.values())) if out else 'no matching places - no effect'

def districts_for(items):
    """website -> council, from overrides/district_cache.json (postcodes.io admin_district, already fetched).
    A postcode that is not in the cache is skipped. Nothing is looked up or invented here."""
    cache = rj('overrides/district_cache.json', {})
    if not isinstance(cache, dict): return {}
    out = {}
    for i in items:
        u = (i.get('website') or '').strip(); pc = (i.get('postcode') or '').upper().strip()
        d = cache.get(pc) or cache.get(pc.replace(' ', ''))
        if u.startswith('http') and d and u not in out: out[u] = d
    return out

def stale_areas(items, state, today):
    """Areas whose checked dates are older than the median area move up. Uses checked_at already on file.
    No cache, or fewer than two areas with a checked date: no effect."""
    areas = districts_for(items)
    if not areas: return {}, 'no council cache (overrides/district_cache.json) - no effect'
    by = collections.defaultdict(list)
    for u, area in areas.items():
        checked = ((state.get('sites') or {}).get(u) or {}).get('checked_at')
        if not checked: continue
        days = learning._days(str(checked), today.isoformat())
        if days >= 10 ** 5: continue
        by[area].append((u, days))
    if len(by) < 2: return {}, 'not enough areas with checked dates - no effect'
    age = {a: sorted(d for _, d in rows)[len(rows) // 2] for a, rows in by.items()}
    med, hi = sorted(age.values())[len(age) // 2], max(age.values())
    if hi <= med: return {}, 'no area is older than the median checked date - no effect'
    span = float(hi - med); out = {}
    for a, rows in by.items():
        if age[a] <= med: continue
        factor = (age[a] - med) / span
        for u, _ in rows: out[u] = round(max(out.get(u, 0), factor), 3)
    return out, '%d areas; those older than the median checked date move up' % len(age)

def _documented_dates(obj):
    """A calendar counts only when it names an http(s) source and lists dates. Otherwise it is ignored."""
    if not isinstance(obj, dict): return False
    src, dates = obj.get('source'), obj.get('dates')
    return isinstance(src, str) and src.startswith('http') and isinstance(dates, list)

def demand_forecast(items, today):
    """Cold snaps, benefit payment dates, school holidays. Real files only.
    Cold snaps: a Met Office warning in reports/weather.json (written by scripts/weather.py) whose title
    mentions snow, ice or cold. Benefit dates: reports/benefit_dates.json with a source URL and a dates list.
    School holidays: reports/holidays.json only when school_holidays is a list AND school_holiday_source is an
    http(s) URL. scripts/holidays.py leaves school holidays out on purpose (no single official UK list), so
    that string note has no effect. This function never writes dates."""
    notes, per = [], {}
    areas = districts_for(items)
    wx = rj('reports/weather.json', None)
    cold_areas = []
    if not isinstance(wx, dict):
        notes.append('cold snaps: no reports/weather.json from scripts/weather.py - no effect')
    else:
        for w in wx.get('warnings') or []:
            blob = '%s %s' % (w.get('title') or '', w.get('level') or '')
            if any(word in blob.lower() for word in COLD_WORDS): cold_areas.extend(w.get('areas') or [])
        if not cold_areas:
            notes.append('cold snaps: no snow, ice or cold warning in reports/weather.json - no effect')
        else:
            import weather as WX
            n = 0
            for u, d in areas.items():
                if any(WX.hits(a, d) or WX.hits(d, a) for a in cold_areas):
                    per[u] = 1.0; n += 1
            notes.append('cold snaps: Met Office warnings via scripts/weather.py (%d places)' % n)
    ben = rj('reports/benefit_dates.json', None)
    if not _documented_dates(ben):
        notes.append('benefit payment dates: no documented calendar (reports/benefit_dates.json needs an http(s) source and a dates list) - no effect')
    else:
        window = []
        for raw in ben['dates']:
            try: dd = datetime.date.fromisoformat(str(raw)[:10])
            except Exception: continue
            if 0 <= (dd - today).days <= 3: window.append(dd.isoformat())
        if not window:
            notes.append('benefit payment dates: nothing in the next 3 days (%s) - no effect' % ben['source'])
        else:
            for i in items:
                u = (i.get('website') or '').strip()
                if u.startswith('http'): per[u] = min(1.0, per.get(u, 0) + 0.5)
            notes.append('benefit payment dates: %s (%s)' % (', '.join(window), ben['source']))
    hol = rj('reports/holidays.json', {})
    sch = hol.get('school_holidays') if isinstance(hol, dict) else None
    src = hol.get('school_holiday_source') if isinstance(hol, dict) else None
    if not (isinstance(sch, list) and isinstance(src, str) and src.startswith('http')):
        notes.append('school holidays: %s - no effect' % (sch if isinstance(sch, str) else 'no documented school-holiday calendar'))
    else:
        hit = False
        for block in sch:
            if not isinstance(block, dict): continue
            try:
                start, end = datetime.date.fromisoformat(block['start'][:10]), datetime.date.fromisoformat(block['end'][:10])
            except Exception: continue
            if not (start <= today <= end): continue
            hit = True; where = (block.get('nation') or block.get('council') or '').lower()
            for u, d in areas.items():
                if not where or where in d.lower() or d.lower() in where:
                    per[u] = min(1.0, per.get(u, 0) + 0.5)
        notes.append('school holidays: %s (%s)' % ('in force' if hit else 'none today', src))
    return per, ' '.join(notes)

def source_watch():
    """A source that failed its last three recorded runs is named for Dean. Places stay on the map.
    No health file yet: no effect. A short outage (fewer than three failures) is not called gone."""
    h = rj('reports/source_health.json', None)
    if not isinstance(h, dict) or not h: return [], 'no source health file yet - no effect'
    gone = learning.sources_gone(h)
    if not gone: return [], 'no source has failed three runs in a row - no effect'
    return gone, 'flagged for Dean, places not removed: ' + ', '.join(gone)

def empty_parses(state):
    """Sites whose own page answered HTTP 200 but the parser found nothing, after a run that had found records.
    The flag moves them up the next check. It does not remove them. No such site: no effect."""
    sites = {u: 1.0 for u, s in (state.get('sites') or {}).items() if s.get('empty_parse')}
    if not sites: return {}, 'no page answered with an empty parser result - no effect'
    return sites, '%d sites answered but the parser found nothing, after a run that had found records' % len(sites)

def weather_priority(items):
    """Councils named in reports/weather.json (written by scripts/weather.py) move up the next run.
    No weather file, or a warning with no area: no effect. Areas are not guessed."""
    wx = rj('reports/weather.json', None)
    if not isinstance(wx, dict) or not wx.get('warnings'):
        return {}, {}, 'no weather warnings on file (reports/weather.json from scripts/weather.py) - no effect'
    areas_named = [a for w in wx['warnings'] for a in (w.get('areas') or []) if a]
    if not areas_named:
        return {}, {}, 'weather warnings have no areas - no effect'
    import weather as WX
    sites = {}
    for u, d in districts_for(items).items():
        if any(WX.hits(a, d) or WX.hits(d, a) for a in areas_named): sites[u] = 1.0
    councils = {}
    for c in (rj('scripts/sweep_sources.json', {}).get('councils') or []):
        name = c.get('name') or ''
        if name and any(WX.hits(a, name) or WX.hits(name, a) for a in areas_named): councils[name] = 1.0
    note = 'weather warnings cover %d councils and %d food-bank sites' % (len(councils), len(sites))
    return sites, councils, note

def council_boosts():
    """For sweep_daily.py: last run's boost per council name."""
    return rj('reports/learning_signals.json', {}).get('council_boost', {})

def crawl_timing(state, LS):
    """Per-host failure rate (and latency where recorded). Slow / failing hosts are spread out, never dropped."""
    f, n = collections.Counter(), collections.Counter()
    for u, s in state.get('sites', {}).items():
        h = host(u); n[h] += 1; f[h] += bool(s.get('fail_runs'))
    lat = LS.get('host_latency', {})
    return {h: {'sites': n[h], 'fail_rate': round(f[h] / n[h], 3), 'avg_s': lat.get(h)} for h in n if n[h] > 1 or f[h]}

def weights(prev, review):
    """Weekly self-review: a component whose boosted checks found more than average gets +STEP, less gets -STEP, within bounds."""
    w = dict(prev or DEFAULT_W)
    for k, base in DEFAULT_W.items():
        r = review.get(k)
        if r is None: continue
        w[k] = round(min(base * HI, max(base * LO, w.get(k, base) * (1 + STEP if r > 0 else 1 - STEP if r < 0 else 1))), 4)
    return w

def accuracy_grades(LS, prev, today):
    """Weekly self-grade: of the places a signal moved up, what share produced a find in the last 7 days,
    compared with the places it did not move. Weak (below 90% of the others, and at least 5 places each)
    is turned down one step. Not enough data: no change. This does not turn a signal up."""
    out = {}; K = LS.get('keys', {}); since = (today - datetime.timedelta(days=7)).isoformat()
    for comp, keys in (prev.get('boosted_by') or {}).items():
        keys = [k for k in keys if k in K]; rest = [k for k in K if k not in set(keys)]
        if len(keys) < 5 or len(rest) < 5:
            out[comp] = {'grade': None, 'weak': False, 'note': 'not enough data'}; continue
        rate = lambda ks: sum(1 for k in ks if (K[k].get('last_find') or '') >= since) / float(len(ks))
        a, b = rate(keys), rate(rest); weak = a < b * 0.9
        out[comp] = {'grade': round(a, 3), 'others': round(b, 3), 'weak': weak, 'note': 'turned down' if weak else 'kept'}
    return out

def self_review(LS, prev_signals, today):
    """Did last week's boosted keys produce finds at a higher rate than the rest? +1 / -1 / None (not enough data)."""
    out = {}; K = LS.get('keys', {}); since = (today - datetime.timedelta(days=7)).isoformat()
    for comp, keys in (prev_signals.get('boosted_by', {}) or {}).items():
        keys = [k for k in keys if k in K]; rest = [k for k in K if k not in set(keys)]
        if len(keys) < 5 or len(rest) < 5: out[comp] = None; continue
        rate = lambda ks: sum(1 for k in ks if (K[k].get('last_find') or '') >= since) / len(ks)
        a, b = rate(keys), rate(rest); out[comp] = 1 if a > b * 1.1 else (-1 if a < b * 0.9 else 0)
    return out

def build(today=None):
    today = today or datetime.date.today(); items = [i for i in items_of('data.full.js') if i.get('type') == 'foodbank']
    state = rj('reports/full_check_state.json', {'sites': {}}); LS = learning.load(learning.STATE); prev = rj('reports/learning_signals.json', {})
    cids, corr_rate = corrections(items); blame = source_blame(items); agree, agree_n, per_site = agreement(items, state); sig = change_signals(items, state)
    rows = conflicts(items, state); conflicted = {r['website'] for r in rows}
    season, weeks, season_note = seasonal(today); dem, dem_note = demand(items); vis, vis_note = visitor(items)
    dean_sites, dean_wording, dean_note = dean_learning(items); problems, problem_note = problem_reports(items)
    stale, stale_note = stale_areas(items, state, today); forecast, forecast_note = demand_forecast(items, today)
    wx_sites, wx_councils, wx_note = weather_priority(items)
    empty_sites, empty_note = empty_parses(state)
    gone, gone_note = source_watch()
    trust = {s: round(max(0.0, min(1.0, agree.get(s, 0.5) - corr_rate.get(s, 0.0))), 4) for s in set(agree) | set(corr_rate)}
    sunday = today.weekday() == 6; review = self_review(LS, prev, today) if sunday else {}
    grades = accuracy_grades(LS, prev, today) if sunday else {}
    if sunday:
        for k, g in grades.items():
            if g.get('weak'): review[k] = -1  # one step down; a weak signal is not also turned up
    stored = prev.get('weights') or {}
    W = {k: stored.get(k, base) for k, base in DEFAULT_W.items()}  # a new signal starts at its default
    if sunday: W = weights(W, review)
    by_site = collections.defaultdict(list)
    for i in items:
        if (i.get('website') or '').startswith('http'): by_site[i['website'].strip()].append(i)
    corr_hosts = {host(i.get('website')) for i in items if i['id'] in cids}
    boost, why, boosted_by = {}, {}, collections.defaultdict(list)
    for u, its in by_site.items():
        src = source_of(its[0]); parts = {}
        if any(i['id'] in cids for i in its) or host(u) in corr_hosts: parts['correction'] = W['correction']
        if u in sig: parts['signal'] = W['signal']
        if per_site.get(u) is False: parts['signal'] = max(parts.get('signal', 0), W['signal'] * 0.75)  # stored phone not on own site
        parts['trust'] = W['trust'] * (1 - trust.get(src, 0.5))  # less-trusted source = check more
        if season: parts['season'] = W['season'] * season
        if dem.get(u): parts['demand'] = W['demand'] * dem[u]
        if vis.get(u): parts['visitor'] = W['visitor'] * min(vis[u], 3) / 3
        rf = learning.rhythm_factor(LS.get('keys', {}).get(u) or {}, today.isoformat())
        if rf: parts['rhythm'] = W['rhythm'] * rf
        if u in dean_sites: parts['dean'] = W['dean']  # priority only; publishing still asks Dean
        if problems.get(u): parts['problem'] = W['problem'] * min(problems[u], 3) / 3
        if stale.get(u): parts['stale_area'] = W['stale_area'] * stale[u]
        if forecast.get(u): parts['forecast'] = W['forecast'] * forecast[u]
        if u in conflicted: parts['conflict'] = W['conflict']
        if wx_sites.get(u): parts['weather'] = W['weather'] * wx_sites[u]
        if empty_sites.get(u): parts['empty_parse'] = W['empty_parse'] * empty_sites[u]
        capped = learning.cap_parts(parts)  # every signal shares BOOST_CAP; none of them raises it
        b = round(sum(capped.values()), 4)
        if b > 0: boost[u] = min(b, learning.BOOST_CAP); why[u] = {k: round(v, 3) for k, v in capped.items() if round(v, 3)}
        for k, v in parts.items():
            if v and k != 'trust': boosted_by[k].append(u)
    # weekly accuracy trend (real measures only): share of reachable sites, phone agreement, hand corrections
    ok = sum(1 for s in state.get('sites', {}).values() if not s.get('fail_runs')); n = len(state.get('sites', {})) or 1
    pt = {'day': today.isoformat(), 'reachable': round(ok / n, 4), 'phone_agreement': round(sum(per_site.values()) / len(per_site), 4) if per_site else None, 'corrections': len(cids)}
    trend = [t for t in prev.get('trend', []) if t.get('day') != pt['day']] + [pt]
    out = dict(run=today.isoformat(), weights=W, review=review, trust=trust, agreement_n=agree_n, correction_rate=corr_rate,
               signals=sig, source_blame=blame, season=dict(boost=season, weeks=weeks, note=season_note), demand_note=dem_note, visitor_note=vis_note,
               hosts=crawl_timing(state, LS), boost=boost, why=why, boosted_by={k: sorted(v) for k, v in boosted_by.items()},
               dean_wording=dean_wording, dean_note=dean_note, problem_note=problem_note, stale_note=stale_note,
               forecast_note=forecast_note, weather_note=wx_note, empty_note=empty_note, source_gone=gone, source_gone_note=gone_note,
               council_boost={k: round(W['weather'] * v, 3) for k, v in wx_councils.items()},
               conflicts=rows, accuracy=grades,
               healed=sorted(k for k, e in (LS.get('keys') or {}).items() if e.get('healed_to'))[:40],
               trend=trend[-60:], discovery='all new places held for Dean (overrides/auto_apply_rules.json add_new_places=false)')
    return out

def write(out):
    tmp = OUT + '.tmp'; json.dump(out, open(tmp, 'w', encoding='utf-8'), indent=0, sort_keys=True); os.replace(tmp, OUT)
    open(MD, 'w', encoding='utf-8').write('\n'.join(digest_lines(out, full=True)) + '\n')
    extra = {'signal_weights': out.get('weights'), 'dean_wording': out.get('dean_wording') or {}, 'accuracy': out.get('accuracy') or {}, 'source_blame': out.get('source_blame') or {}}
    s = learning.load(learning.STATE); learning.note_signals(s, out.get('run'), extra); learning.save(s, learning.STATE)

def weekly(trend):
    """Average per ISO week of the daily accuracy points."""
    g = collections.defaultdict(list)
    for t in trend:
        d = datetime.date.fromisoformat(t['day']); g['%d-W%02d' % d.isocalendar()[:2]].append(t)
    f = lambda xs, k: round(sum(x[k] for x in xs if x.get(k) is not None) / max(1, sum(1 for x in xs if x.get(k) is not None)), 3)
    return [(w, f(xs, 'reachable'), f(xs, 'phone_agreement'), xs[-1]['corrections']) for w, xs in sorted(g.items())]

def digest_lines(out, full=False):
    """Plain-English signals section for the morning note. The same numbers, in sentences."""
    L = ['## What the system learned (signals)', '']
    season = out.get('season') or {}
    T = sorted(out.get('trust', {}).items(), key=lambda x: x[1])
    agreed = out.get('agreement_n') or {}
    trust_bits = ', '.join('%s scores %.2f from %s places checked' % (s, v, agreed.get(s, 0)) for s, v in T)
    L.append('- How far each source can be trusted (its phone matches the place\'s own website, after your hand corrections): ' + (trust_bits or 'none yet'))
    blame = out.get('source_blame') or {}
    blame_bits = ', '.join('%s (%s)' % (s, ', '.join('%s %d' % kv for kv in sorted(v.items()))) for s, v in sorted(blame.items()))
    L.append('- Hand corrections, counted against the source that supplied the place: ' + (blame_bits or 'none recorded'))
    L.append('- Places that look like they may have changed (a dead link, closure wording, a Facebook problem, or a bounced email): %d' % len(out.get('signals', {})))
    bb = out.get('boosted_by') or {}
    L.append('- Places moved earlier in the next check: %d in total. Of those, %d follow a hand correction, %d a change signal, %d the time of year, %d visitor demand, %d a visitor report, and %d how often that place usually changes.' % (
        len(out.get('boost') or {}), len(bb.get('correction') or []), len(bb.get('signal') or []), len(bb.get('season') or []),
        len(bb.get('demand') or []), len(bb.get('visitor') or []), len(bb.get('rhythm') or [])))
    L.append('- Time of year: the extra priority this week is %.2f. %s' % (season.get('boost', 0), season.get('note', '')))
    L.append('- Visitor demand: ' + (out.get('demand_note') or '') + '. Visitor reports: ' + (out.get('visitor_note') or ''))
    L.append("- What your past decisions taught the queue (you are still asked every time): " + out.get('dean_note', 'no hand decisions to learn from yet - no effect'))
    L.append('- Report a problem submissions: ' + out.get('problem_note', 'no Report a problem submissions on file - no effect'))
    L.append('- Areas whose last check is older than the others: ' + (out.get('stale_note') or ''))
    L.append('- Cold snaps, benefit payment dates and school holidays: ' + (out.get('forecast_note') or ''))
    L.append('- Weather warnings: ' + (out.get('weather_note') or ''))
    L.append('- Pages that answered but the parser found nothing: ' + (out.get('empty_note') or 'no effect'))
    L.append('- Sources that have stopped answering: ' + (out.get('source_gone_note') or 'no effect'))
    L.append('- Sources disagree on %d places. Nothing was picked; they are flagged for Dean.' % len(out.get('conflicts') or []))
    L.append('- Fetches that switched to a method which had already worked for that site: %d' % len(out.get('healed') or []))
    slow = sorted((out.get('hosts') or {}).items(), key=lambda x: -x[1]['fail_rate'])[:3]
    hard = ', '.join('%s (%d of every 100 checks fail, across %d sites)' % (h, round(v['fail_rate'] * 100), v['sites']) for h, v in slow if v['fail_rate'])
    L.append('- Websites that are hardest to reach: ' + (hard or 'none'))
    words = {1: 'found more than the rest, so its weight rose by one step', -1: 'found less than the rest, so its weight fell by one step', 0: 'no change this week', None: 'not enough data yet'}
    if out.get('review'): L.append('- Sunday check of whether each signal earned its place: ' + ', '.join('%s %s' % (k, words[v]) for k, v in out['review'].items()))
    if out.get('accuracy'): L.append('- Sunday accuracy grade (a weak signal is turned down, never turned up by this grade): ' + ', '.join('%s: %s' % (k, v.get('note')) for k, v in sorted(out['accuracy'].items())))
    wk = weekly(out.get('trend') or [])
    if wk:
        bits = '; '.join('%s: %d of every 100 sites answered, phones agreed %s, and there were %d hand corrections' % (
            w, round(r * 100), ('%d of every 100' % round(p * 100)) if p else 'on too few places to say', c) for w, r, p, c in wk[-4:])
        L.append('- How the last few weeks went: ' + bits)
    else:
        L.append('- How the last few weeks went: this is the first week, so there is no trend yet.')
    L.append('- A new place is never added on its own. It waits in reports/pending_dean.md until you say yes.')
    if full:
        L += ['', '### How strongly each signal counts (kept between %.0f%% and %.0f%% of its starting weight, and moved by at most %.0f%% a week)' % (LO * 100, HI * 100, STEP * 100), '']
        L += ['- %s: %.3f' % kv for kv in sorted((out.get('weights') or {}).items())]
        L += ['', '### The 20 places moved up the most', '']
        L += ['- %s: %s' % (u, (out.get('why') or {}).get(u)) for u, _ in sorted((out.get('boost') or {}).items(), key=lambda x: -x[1])[:20]]
    return L + ['']

def boosts():
    """For full_check.py: last run's boost per site (0 when there is no file yet)."""
    return rj('reports/learning_signals.json', {}).get('boost', {})

if __name__ == '__main__':
    o = build(); write(o); print('learning signals: %d boosted, %d signals, trust %s' % (len(o['boost']), len(o['signals']), o['trust']))
