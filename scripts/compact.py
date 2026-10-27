"""Write the compact, browser-facing data.js from the canonical data.full.js (Dean, 22 Oct: halve bandwidth per visitor).
Scripts read/write data.full.js (full format, window.FB_DATA={...}); only the app loads data.js.
data.js decodes itself back to window.FB_DATA={fetched,source,items:[...]} with exactly the fields the app reads,
so index.html / layers.js / v3.js are unchanged. Stdlib only."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(ROOT, 'data.full.js'); OUT = os.path.join(ROOT, 'data.js')
# fields the app reads (index.html, layers.js, v3.js); everything else is pipeline bookkeeping
KEYS = ['id', 'type', 'name', 'foodbank', 'postcode', 'address', 'lat', 'lng', 'phone', 'tel', 'website', 'givefood', 'opening_times',
        'kind', 'label_en', 'label_cy', 'centres', 'moved_to_postcode', 'phone_checked', 'locked', 'manual', 'evidence_url', 'fb_page', 'phone_label', 'notice',
        'source_label', 'venues_vary', 'service_lat', 'service_lng', 'service_km']
OT = ['status', 'structured', 'all_closed', 'checked_date', 'source_url', 'raw', 'lines']
GF = 'https://www.givefood.org.uk/needs/at/%s/'
M = '~'  # "field absent" marker (never a real value: checked below)
# columns (one array per key) compress far better than rows; refs: tel/givefood/foodbank 1 = same as phone/standard URL/name,
# address ending in the "\u00a7" sign = ", <postcode>" stripped, opening_times.source_url 1 = website
DEC = ("(function(c){var K=c.k,C=c.c,G=c.g,n=c.n,it=[],i,j;for(i=0;i<n;i++){var o={};for(j=0;j<K.length;j++){var k=K[j],v=C[k][i];"
       "if(v===undefined||v==='~')continue;if(v===1&&k==='tel')v=o.phone;else if(v===1&&k==='givefood')v=G.replace('%s',o.id);"
       "else if(v===1&&k==='foodbank')v=o.name;else if(k==='address'&&v.slice(-1)==='\\u00a7')v=v.slice(0,-1)+', '+o.postcode;"
       "else if(k==='opening_times'&&v&&v.source_url===1)v.source_url=o.website;o[k]=v}it.push(o)}it.forEach(function(o){if(o.centres)o.centres=o.centres.map(function(x){if(typeof x!=='number')return x;"
       "var t=it[x];return {id:t.id,name:t.name,address:t.address,lat:t.lat,lng:t.lng}})});"
       "window.FB_DATA={fetched:c.f,source:c.s,items:it}})")
R5 = lambda v: round(v, 5) if isinstance(v, float) else v

def load_full(p=FULL):
    s = open(p, encoding='utf-8').read(); return json.loads(s[s.index('=') + 1:].rstrip().rstrip(';'))

def enc(i, k):
    if k not in i: return M
    v = i[k]
    if v == M or v == 1 and k in ('tel', 'givefood', 'foodbank', 'address'): raise ValueError('marker clash %s %s' % (i.get('id'), k))
    if k in ('lat', 'lng', 'service_lat', 'service_lng'): return R5(v)
    if k == 'tel' and v == i.get('phone'): return 1
    if k == 'givefood' and v == GF % i['id']: return 1
    if k == 'foodbank' and v == i.get('name'): return 1
    if k == 'address' and isinstance(v, str):
        if v.endswith('\u00a7'): raise ValueError('marker clash address')
        pc = i.get('postcode')
        if pc and v.endswith(', ' + pc): return v[:-len(pc) - 2] + '\u00a7'
    if k == 'centres' and isinstance(v, list):  # a centre that is also a pin (same id/name/address/coords) -> its index
        out = []
        for c in v:
            j = IDX.get(c.get('id')) if isinstance(c, dict) else None
            t = ITEMS[j] if j is not None else None
            same = t is not None and set(c) == {'id', 'name', 'address', 'lat', 'lng'} and all(t.get(x) == c[x] for x in c)
            out.append(j if same else ({x: R5(y) for x, y in c.items()} if isinstance(c, dict) else c))
        return out
    if k == 'opening_times' and isinstance(v, dict):
        v = {x: v[x] for x in OT if x in v}
        st = v.get('status')  # the app only reads raw/lines for TIMES_TEXT_ONLY and structured/all_closed for TIMES_FOUND
        if st != 'TIMES_FOUND': v.pop('structured', None); v.pop('all_closed', None)
        if st != 'TIMES_TEXT_ONLY': v.pop('raw', None); v.pop('lines', None)
        elif v.get('lines') and v.get('raw'): v['raw'] = 1  # only its truthiness is read when lines exist
        if st not in ('TIMES_FOUND', 'TIMES_TEXT_ONLY'): v.pop('source_url', None)
        if v.get('source_url') and v.get('source_url') == i.get('website'): v['source_url'] = 1
    return v

def encode(meta):
    global ITEMS, IDX
    it = ITEMS = meta['items']; IDX = {i['id']: n for n, i in enumerate(it)}
    cols = {k: [enc(i, k) for i in it] for k in KEYS}
    for k in KEYS:  # trailing absents can be dropped (undefined in JS)
        c = cols[k]
        while c and c[-1] == M: c.pop()
    c = dict(f=meta.get('fetched'), s=meta.get('source'), g=GF, n=len(it), k=KEYS, c=cols)
    return DEC + '(' + json.dumps(c, separators=(',', ':'), ensure_ascii=False) + ');\n'

def main():
    out = encode(load_full())
    t = OUT + '.tmp'; open(t, 'w', encoding='utf-8').write(out); os.replace(t, OUT)
    print('compact data.js: %d bytes (full %d)' % (len(out.encode()), os.path.getsize(FULL)))

if __name__ == '__main__': main()
