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
    for i in items:
        i['opening_times'] = times.get(i['id'])
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
    cur = current_count()
    if len(items) < 0.8 * cur: die('only %d entries vs %d current (<80%%)' % (len(items), cur))
    meta = dict(fetched=datetime.date.today().isoformat(), source='Give Food API v2 https://www.givefood.org.uk/api/', items=items)
    new = 'window.FB_DATA=' + json.dumps(meta) + ';'
    tmp = OUT + '.tmp'; open(tmp, 'w').write(new); os.replace(tmp, OUT)
    print('wrote %d entries (previous %d)' % (len(items), cur))

if __name__ == '__main__': main()
