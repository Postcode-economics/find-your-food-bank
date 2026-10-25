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
DEFAULT_W = {'correction': 0.5, 'signal': 0.8, 'trust': 0.4, 'season': 0.3, 'demand': 0.3, 'visitor': 0.8}
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

def agreement(items, state):
    """Cross-source agreement: is the stored phone one of the phones on the place's own site? Beta(1,1) per source."""
    ok, n = collections.Counter(), collections.Counter(); per_site = {}
    for i in items:
        s = state.get('sites', {}).get((i.get('website') or '').strip()); p = norm(i.get('tel') or i.get('phone'))
        if not s or not p or not s.get('phones') or s.get('fail_runs'): continue
        hit = p in {norm(x) for x in s['phones']}; src = source_of(i); n[src] += 1; ok[src] += hit; per_site[i['website'].strip()] = hit
    return {s: round((ok[s] + 1) / (n[s] + 2), 4) for s in n}, {s: n[s] for s in n}, per_site

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

def visitor(items):
    v = {k: x for k, x in rj('overrides/visitor_reports.json', {}).items() if not k.startswith('_')}
    by = {i['id']: (i.get('website') or '').strip() for i in items}
    return {by[k]: len(x) for k, x in v.items() if by.get(k)}, ('%d places reported by visitors' % len(v)) if v else 'no visitor reports recorded yet - no effect'

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
    cids, corr_rate = corrections(items); agree, agree_n, per_site = agreement(items, state); sig = change_signals(items, state)
    season, weeks, season_note = seasonal(today); dem, dem_note = demand(items); vis, vis_note = visitor(items)
    trust = {s: round(max(0.0, min(1.0, agree.get(s, 0.5) - corr_rate.get(s, 0.0))), 4) for s in set(agree) | set(corr_rate)}
    sunday = today.weekday() == 6; review = self_review(LS, prev, today) if sunday else {}
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
               signals=sig, season=dict(boost=season, weeks=weeks, note=season_note), demand_note=dem_note, visitor_note=vis_note,
               hosts=crawl_timing(state, LS), boost=boost, why=why, boosted_by={k: sorted(v) for k, v in boosted_by.items()},
               healed=sorted(k for k, e in (LS.get('keys') or {}).items() if e.get('healed_to'))[:40],
               trend=trend[-60:], discovery='all new places held for Dean (overrides/auto_apply_rules.json add_new_places=false)')
    return out

def write(out):
    tmp = OUT + '.tmp'; json.dump(out, open(tmp, 'w', encoding='utf-8'), indent=0, sort_keys=True); os.replace(tmp, OUT)
    open(MD, 'w', encoding='utf-8').write('\n'.join(digest_lines(out, full=True)) + '\n')
    s = learning.load(learning.STATE); learning.note_signals(s, out.get('run'), {'signal_weights': out.get('weights')}); learning.save(s, learning.STATE)

def weekly(trend):
    """Average per ISO week of the daily accuracy points."""
    g = collections.defaultdict(list)
    for t in trend:
        d = datetime.date.fromisoformat(t['day']); g['%d-W%02d' % d.isocalendar()[:2]].append(t)
    f = lambda xs, k: round(sum(x[k] for x in xs if x.get(k) is not None) / max(1, sum(1 for x in xs if x.get(k) is not None)), 3)
    return [(w, f(xs, 'reachable'), f(xs, 'phone_agreement'), xs[-1]['corrections']) for w, xs in sorted(g.items())]

def digest_lines(out, full=False):
    L = ['## What the system learned (signals)', '']
    T = sorted(out.get('trust', {}).items(), key=lambda x: x[1])
    L.append('- Source trust (phone agrees with own site, minus hand corrections): ' + (', '.join('%s %.2f (%s checked)' % (s, v, out['agreement_n'].get(s, 0)) for s, v in T) or 'none yet'))
    L.append('- Places with change signals (dead link, closure wording, Facebook, bounce): %d' % len(out.get('signals', {})))
    L.append('- Checks moved up for next run: %d sites (corrections %d, signals %d, season %d, demand %d, visitor reports %d)' % (
        len(out.get('boost', {})), *(len(out.get('boosted_by', {}).get(k, [])) for k in ('correction', 'signal', 'season', 'demand', 'visitor'))))
    L.append('- Seasonal timing: boost %.2f this week (%s)' % (out['season']['boost'], out['season']['note']))
    L.append('- Demand: ' + out.get('demand_note', '') + '; visitor reports: ' + out.get('visitor_note', ''))
    L.append('- Scrapers that switched to a method which worked before: %d' % len(out.get('healed') or []))
    slow = sorted(out.get('hosts', {}).items(), key=lambda x: -x[1]['fail_rate'])[:3]
    L.append('- Hardest hosts to reach: ' + (', '.join('%s (%d%% of %d sites failing)' % (h, v['fail_rate'] * 100, v['sites']) for h, v in slow if v['fail_rate']) or 'none'))
    if out.get('review'): L.append('- Weekly self-review: ' + ', '.join('%s %s' % (k, {1: 'paid off (+10%)', -1: 'did not pay off (-10%)', 0: 'no change', None: 'not enough data'}[v]) for k, v in out['review'].items()))
    wk = weekly(out.get('trend', []))
    L.append('- Weekly accuracy trend: ' + ('; '.join('%s reachable %.0f%%, phones agree %s, corrections %d' % (w, r * 100, ('%.0f%%' % (p * 100)) if p else 'n/a', c) for w, r, p, c in wk[-4:]) or 'first week'))
    L.append('- New places found are never added automatically: they wait in reports/pending_dean.md for your OK.')
    if full:
        L += ['', '### Weights now (bounded %.0f%%-%.0f%% of default, max %.0f%% change a week)' % (LO * 100, HI * 100, STEP * 100), ''] + ['- %s: %.3f' % kv for kv in sorted(out['weights'].items())]
        L += ['', '### Top 20 boosted sites', ''] + ['- %s: %s' % (u, out['why'].get(u)) for u, _ in sorted(out['boost'].items(), key=lambda x: -x[1])[:20]]
    return L + ['']

def boosts():
    """For full_check.py: last run's boost per site (0 when there is no file yet)."""
    return rj('reports/learning_signals.json', {}).get('boost', {})

if __name__ == '__main__':
    o = build(); write(o); print('learning signals: %d boosted, %d signals, trust %s' % (len(o['boost']), len(o['signals']), o['trust']))
