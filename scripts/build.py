#!/usr/bin/env python3
"""Rebuild data.js from the Give Food API. Stdlib only. Fails safe: data.js is
only replaced if the fetch succeeds and the entry count is >= 80% of the current one."""
import json, math, os, sys, urllib.request, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data.full.js')
UA = {'User-Agent': 'foodbank-map-refresh (github actions)'}
API = 'https://www.givefood.org.uk/api/2/'

def die(msg):
    print('FAIL SAFE:', msg, '- data.js not changed'); sys.exit(1)

def get(url, data=None, tries=3):
    for n in range(tries):
        try:
            h = dict(UA)
            if data is not None: h['Content-Type'] = 'application/json'
            req = urllib.request.Request(url, data=data, headers=h)
            return json.load(urllib.request.urlopen(req, timeout=90))
        except Exception as e:
            err = e
    raise err

def load_json(p, default):
    try: return json.load(open(p))
    except FileNotFoundError: return default

def current_count():
    try:
        s = open(OUT).read(); s = s[s.index('=') + 1:].rstrip().rstrip(';')
        return len(json.loads(s)['items'])
    except Exception: return 0

def load_prev_items():
    try:
        s = open(OUT).read(); s = s[s.index('=') + 1:].rstrip().rstrip(';'); return json.loads(s)['items']
    except Exception: return []

def clean(a): return ', '.join(x.strip() for x in (a or '').replace('\r', '').split('\n') if x.strip())

def hav(a, b, c, d):
    p = math.radians; x = math.sin(p(c-a)/2)**2 + math.cos(p(a))*math.cos(p(c))*math.sin(p(d-b)/2)**2
    return 2*6371*math.asin(math.sqrt(x))

def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fb_recheck
    api_meta = {}
    try:
        fb, api_meta['foodbanks'] = fb_recheck.fetch_api(API + 'foodbanks/'); loc, api_meta['locations'] = fb_recheck.fetch_api(API + 'locations/')
    except Exception as e: die('fetch failed: %r' % e)
    records = {}  # id -> exact source record, hashed per entry by the recheck gate
    if not isinstance(fb, list) or not isinstance(loc, list): die('unexpected API shape')
    fbs = {f['slug']: f for f in fb}
    items = []
    for f in fb:
        if f.get('closed') or not f.get('lat_lng'): continue
        la, ln = map(float, f['lat_lng'].split(','))
        items.append(dict(id=f['slug'], type='foodbank', name=f['name'], foodbank=f['name'], network=f.get('network') or '',
            address=clean(f.get('address')), postcode=(f.get('postcode') or '').upper().strip(), lat=la, lng=ln,
            phone=f.get('phone') or '', website=f['urls'].get('homepage') or '', givefood=f['urls']['html']))
        records[f['slug']] = f
    for l in loc:
        p = fbs.get(l['foodbank']['slug'])
        if p is None or p.get('closed') or not l.get('lat_lng'): continue
        la, ln = map(float, l['lat_lng'].split(','))
        lid = l['foodbank']['slug'] + '/' + (l.get('slug') or l['urls']['html'].rstrip('/').split('/')[-1])
        items.append(dict(id=lid, type='location', name=l['name'], foodbank=p['name'], network=l['foodbank'].get('network') or '',
            address=clean(l.get('address')), postcode=(l.get('postcode') or '').upper().strip(), lat=la, lng=ln,
            phone=l.get('phone') or p.get('phone') or '', website=p['urls'].get('homepage') or '', givefood=l['urls']['html']))
        records[lid] = l
    seen = set(); out = []
    for i in items:
        k = (i['foodbank'].lower(), i['postcode'].replace(' ', ''), round(i['lat'], 4), round(i['lng'], 4))
        if k in seen: continue
        seen.add(k); out.append(i)
    items = out
    for i in items:  # manual fix verified against the food bank's own site
        i['address'] = i['address'].replace('Wayneflete Street', 'Waynflete Street')
    phones = load_json(os.path.join(ROOT, 'overrides', 'phones.json'), {})
    times = load_json(os.path.join(ROOT, 'overrides', 'opening_times.json'), {})
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from times import normalise  # scraped text -> clean Mon-Sun table, or deduped text 'as written'
    for i in items:
        i['opening_times'] = normalise(times.get(i['id']))
        if i['id'] in phones: i['phone'] = phones[i['id']]; i['phone_checked'] = True
    fbp = {k: v for k, v in load_json(os.path.join(ROOT, 'overrides', 'facebook_pages.json'), {}).items() if not k.startswith('_')}
    for i in items:  # verified Facebook page, used only when there is no phone (Dean 23 Oct)
        if i['id'] in fbp: i['fb_page'] = fbp[i['id']]['url']
    names = {k: v for k, v in load_json(os.path.join(ROOT, 'overrides', 'foodbank_names.json'), {}).items() if not k.startswith('_')}
    for i in items:  # names a food bank asked us to use (overrides/foodbank_names.json)
        nm = names.get(i['id'])
        if nm:
            for k in ('name', 'foodbank'):
                if nm.get(k): i[k] = nm[k]
    import own_locations  # own-site locations pages (overrides/own_location_pages.json), re-scraped every run; page beats Give Food
    own_log = own_locations.refresh(items, ROOT); print('own locations pages:', json.dumps(own_log))
    # postcode check: move pins >2 km from their postcode centroid
    pcs = sorted({i['postcode'] for i in items if i['postcode']}); res = {}
    try:
        for s in range(0, len(pcs), 100):
            r = get('https://api.postcodes.io/postcodes', json.dumps({'postcodes': pcs[s:s+100]}).encode())
            for x in r['result']:
                if x['result'] and x['result'].get('latitude'): res[x['query']] = (x['result']['latitude'], x['result']['longitude'])
    except Exception as e:
        print('warning: postcode check skipped:', e); res = None
    for i in items:
        if res is None: break
        r = res.get(i['postcode'])
        i['pc_checked'] = bool(r)
        if r and hav(i['lat'], i['lng'], *r) > 2:
            i['orig_latlng'] = [i['lat'], i['lng']]; i['lat'], i['lng'] = round(r[0], 6), round(r[1], 6); i['moved_to_postcode'] = True
    # classify client-facing vs warehouse/office (manual locks in overrides/foodbank_manual.json always applied)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from classify import classify, write_csv
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    # own-site closure check (own site beats Give Food): omit pins whose own site says they closed; log + 30-day recently-closed list
    import closure, discover, directories
    # ---- discovery (every run): IFAN finder vs what Give Food gave us; Trussell finder is captcha-gated (logged) ----
    disc = {'run': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(), 'sources': {}, 'added': [], 'flagged': []}
    disc['sources']['Give Food API v2'] = {'status': 'ok', 'count': len(items)}
    cands, st = directories.ifan()
    if st['status'] != 'ok':  # fail safe: directory down -> keep last run's IFAN pins as candidates (re-checked on their own site below)
        prev = load_prev_items(); cands = [x for x in prev if x.get('directory') == 'IFAN']; st['kept_from_last_run'] = len(cands)
    disc['sources']['IFAN (foodaidnetwork.org.uk)'] = st
    disc['sources']['Trussell find-a-foodbank'] = directories.trussell()[1]
    new_c, dup = discover.dedupe(cands, items); st['already_on_map'] = dup; st['new_candidates'] = len(new_c)
    import discovery_rules as DR  # Dean's auto-add rule (23 Oct 2026): valid in-area postcode, not a duplicate, working source, current
    live = st.get('status') == 'ok'
    for c in new_c:
        c['source_live'] = live
        if c.get('lat') is not None: c.setdefault('src_lat', c['lat']); c.setdefault('src_lng', c['lng'])
    try: GEO = {discover.norm_pc(k): v for k, v in discover.geocode([c.get('postcode') for c in new_c if c.get('postcode')]).items()}
    except Exception: GEO = {}
    RUN_DAY = datetime.date.today().isoformat()
    def chk(c):
        r = {'result': 'flag', 'reasons': []} if DR.held(c) else discover.own_site_check(c, 'fb')
        return c, r, DR.assess(c, r, GEO, RUN_DAY)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(24) as ex: res = list(ex.map(chk, new_c))
    if sum(1 for x in res if x[2][0] == 'add') > int(os.environ.get('DISCOVERY_MAX_NEW', '150')):  # flood = source changed: hold all
        res = [(c, r, ('queue', ['held: too many new in one run'])) for c, r, _ in res]
    disc['rejected'] = []
    for c, r, (decision, why) in res:
        ev = {k: r.get(k) for k in ('url', 'final_url', 'http', 'sha256', 'etag', 'last_modified')}
        if decision == 'reject':
            disc['rejected'].append({'id': c['id'], 'name': c['name'], 'postcode': c.get('postcode'), 'website': c.get('website'), 'reasons': why}); continue
        if decision == 'add':
            c = {k: v for k, v in c.items() if k not in ('src_lat', 'src_lng', 'source_live')}
            if c.get('lat') is None and discover.norm_pc(c.get('postcode')) in GEO: c['lat'], c['lng'] = GEO[discover.norm_pc(c['postcode'])]
            c = dict(c, type='foodbank', address=c.get('address') or c['postcode'], phone='', givefood='', opening_times=None,
                     discovered=disc['run'][:10], own_site_check=ev)
            records[c['id']] = {k: v for k, v in c.items() if k != 'own_site_check'}
            items.append(c); disc['added'].append({'id': c['id'], 'name': c['name'], 'postcode': c['postcode'], **ev})
        else:
            disc['flagged'].append({'id': c['id'], 'name': c['name'], 'postcode': c.get('postcode'), 'website': c.get('website'), 'directory': c.get('directory'), 'reasons': why or r['reasons'], **ev})
    # Give Food entries that are new since the last published run are logged as added too (Give Food is the primary feed)
    try:
        prev_ids = {x['id'] for x in load_prev_items()}
        gf_new = [{'id': x['id'], 'name': x.get('name'), 'postcode': x.get('postcode'), 'source_url': 'https://www.givefood.org.uk/needs/at/' + x['id'].split('/')[0] + '/'} for x in items if prev_ids and x['id'] not in prev_ids and not x.get('directory')]
    except Exception: gf_new = []
    DR.record('foodbanks', RUN_DAY, gf_new + disc['added'], disc['flagged'], disc['rejected'], source='Give Food + IFAN')
    # own-site closure check (own site beats Give Food) - shares this run's page cache
    gone = closure.apply(items, ROOT, fetcher=discover.closure_fetcher)
    if gone: print('omitted as closed on own site:', ', '.join(gone))
    # times cross-check on every pin's OWN site this run: confirmed / updated / unconfirmed (withheld, never carried over)
    tlog = discover.cross_check_times(items, 'fb', 'opening_times')
    held = [i['id'] for i in items if i.pop('_own_site_closed', None)]
    disc['times'] = discover.summary(tlog); disc['own_site_says_closed_held'] = held
    json.dump(tlog, open(os.path.join(ROOT, 'logs', 'foodbank_times_check.json'), 'w'), indent=0, ensure_ascii=False)
    json.dump(disc, open(os.path.join(ROOT, 'logs', 'foodbank_discovery.json'), 'w'), indent=1, ensure_ascii=False)
    print('discovery: %d new candidates, %d added, %d flagged; times %s' % (len(new_c), len(disc['added']), len(disc['flagged']), disc['times']))
    import hours_norm  # stored opening_times: structured in Mon-Sun order, text lines once (part of every refresh)
    n_ot = hours_norm.apply(items, 'opening_times')
    write_csv(classify(items, ROOT), os.path.join(ROOT, 'logs', 'foodbank_audit.csv'))
    from hours_fix import apply_phone  # split 'a or b' / '%2F', strip HTML, fix leading 0, UK-format check; tel = first valid
    for i in items: apply_phone(i)
    # recheck gate: same over-check as shelters / warm spaces (hash + fetched_at, HTTP, ETag/Last-Modified, schema, source URL)
    extra = load_json(os.path.join(ROOT, 'overrides', 'foodbank_extra_locations.json'), {})
    extra.update(load_json(os.path.join(ROOT, 'overrides', 'foodbank_own_pages.json'), {}))
    extra.update({k: v for k, v in load_json(os.path.join(ROOT, 'overrides', 'foodbank_added.json'), {}).items() if not k.startswith('_')})  # hand-added food banks (Dean 24 Oct): the checked record is their source
    for i in items:
        if i.get('manual') and i['id'] in extra: records[i['id']] = extra[i['id']]  # source = the human-checked own-site record
    allc = {i['id']: i.pop('_own_all_closed') for i in items if '_own_all_closed' in i}  # kept out of the recheck gate
    before = len(items)
    try:
        items, omitted = fb_recheck.gate(items, records, api_meta, os.path.join(ROOT, 'logs', 'foodbank_recheck.json'), os.path.join(ROOT, 'logs', 'foodbank_pending.json'))
    except RuntimeError as e: die(str(e))
    print('recheck gate: %d of %d published, %d omitted; opening_times normalised on %d' % (len(items), before, len(omitted), n_ot))
    show_closed = set(load_json(os.path.join(ROOT, 'overrides', 'show_all_closed.json'), {}).get('ids', []))
    for i in items:  # per-pin: own page lists every day 'Closed' -> publish a Mon-Sun table of 'Closed' (only for ids in the override)
        ac = allc.get(i['id'])
        if ac and i['id'] in show_closed: i['opening_times'] = dict(ac, status='TIMES_FOUND', structured=None, all_closed=True)
    excl = load_json(os.path.join(ROOT, 'overrides', 'foodbank_exclude.json'), {}).get('foodbanks', [])
    def excluded(i):
        host = (i.get('website') or '').split('//')[-1].split('/')[0].lower().removeprefix('www.')
        return any(i['id'] == e['slug'] or (not e.get('exact') and (i['id'].startswith(e['slug'] + '/') or (e.get('host') and host == e['host']))) for e in excl)
    n0 = len(items); items = [i for i in items if not excluded(i)]
    print('excluded at request: %d pins' % (n0 - len(items)))
    cur = current_count()
    if len(items) < 0.8 * cur: die('only %d entries vs %d current (<80%%)' % (len(items), cur))
    # Verified Facebook pages again here, AFTER IFAN discovery adds its pins (24 Oct: 16 IFAN pages were lost
    # because the earlier pass ran before IFAN entries existed). Only shown when the card has no phone (index.html).
    for i in items:
        if i['id'] in fbp: i['fb_page'] = fbp[i['id']]['url']
    meta = dict(fetched=datetime.date.today().isoformat(), source='Give Food API v2 https://www.givefood.org.uk/api/ + IFAN https://www.foodaidnetwork.org.uk/ (own-site checked)', items=items)
    new = 'window.FB_DATA=' + json.dumps(meta) + ';'
    if os.environ.get('DRY_RUN'): print('DRY RUN: %d entries (previous %d), data.js not written' % (len(items), cur)); return
    tmp = OUT + '.tmp'; open(tmp, 'w').write(new); os.replace(tmp, OUT)
    print('wrote %d entries (previous %d)' % (len(items), cur))
    import compact; compact.main()  # browser-facing compact data.js
    import build_access; build_access.main(ROOT)  # filter chips: regenerate access.js from overrides/access/*.csv

if __name__ == '__main__': main()
