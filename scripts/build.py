#!/usr/bin/env python3
"""Rebuild data.js from the Give Food API. Stdlib only. Fails safe: data.js is
only replaced if the fetch succeeds and the entry count is >= 80% of the current one."""
import json, math, os, sys, urllib.request, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data.js')
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
    try:
        fb = get(API + 'foodbanks/'); loc = get(API + 'locations/')
    except Exception as e: die('fetch failed: %r' % e)
    if not isinstance(fb, list) or not isinstance(loc, list): die('unexpected API shape')
    fbs = {f['slug']: f for f in fb}
    items = []
    for f in fb:
        if f.get('closed') or not f.get('lat_lng'): continue
        la, ln = map(float, f['lat_lng'].split(','))
        items.append(dict(id=f['slug'], type='foodbank', name=f['name'], foodbank=f['name'], network=f.get('network') or '',
            address=clean(f.get('address')), postcode=(f.get('postcode') or '').upper().strip(), lat=la, lng=ln,
            phone=f.get('phone') or '', website=f['urls'].get('homepage') or '', givefood=f['urls']['html']))
    for l in loc:
        p = fbs.get(l['foodbank']['slug'])
        if p is None or p.get('closed') or not l.get('lat_lng'): continue
        la, ln = map(float, l['lat_lng'].split(','))
        lid = l['foodbank']['slug'] + '/' + (l.get('slug') or l['urls']['html'].rstrip('/').split('/')[-1])
        items.append(dict(id=lid, type='location', name=l['name'], foodbank=p['name'], network=l['foodbank'].get('network') or '',
            address=clean(l.get('address')), postcode=(l.get('postcode') or '').upper().strip(), lat=la, lng=ln,
            phone=l.get('phone') or p.get('phone') or '', website=p['urls'].get('homepage') or '', givefood=l['urls']['html']))
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
    def chk(c): return c, discover.own_site_check(c, 'fb')
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(24) as ex: res = list(ex.map(chk, new_c))
    for c, r in res:
        ev = {k: r.get(k) for k in ('url', 'final_url', 'http', 'sha256', 'etag', 'last_modified')}
        if r['result'] == 'add':
            c = dict(c, type='foodbank', address=c.get('address') or c['postcode'], phone='', givefood='', opening_times=None,
                     discovered=disc['run'][:10], own_site_check=ev)
            items.append(c); disc['added'].append({'id': c['id'], 'name': c['name'], 'postcode': c['postcode'], **ev})
        else:
            disc['flagged'].append({'id': c['id'], 'name': c['name'], 'postcode': c['postcode'], 'website': c.get('website'), 'directory': c['directory'], 'reasons': r['reasons'], **ev})
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
    write_csv(classify(items, ROOT), os.path.join(ROOT, 'logs', 'foodbank_audit.csv'))
    cur = current_count()
    if len(items) < 0.8 * cur: die('only %d entries vs %d current (<80%%)' % (len(items), cur))
    meta = dict(fetched=datetime.date.today().isoformat(), source='Give Food API v2 https://www.givefood.org.uk/api/ + IFAN https://www.foodaidnetwork.org.uk/ (own-site checked)', items=items)
    new = 'window.FB_DATA=' + json.dumps(meta) + ';'
    if os.environ.get('DRY_RUN'): print('DRY RUN: %d entries (previous %d), data.js not written' % (len(items), cur)); return
    tmp = OUT + '.tmp'; open(tmp, 'w').write(new); os.replace(tmp, OUT)
    print('wrote %d entries (previous %d)' % (len(items), cur))

if __name__ == '__main__': main()
