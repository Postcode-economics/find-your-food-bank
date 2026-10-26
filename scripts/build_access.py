#!/usr/bin/env python3
"""Regenerate access.js (id -> voucher|walkin|unconfirmed) for the filter chips.
Source: overrides/access/voucher_split_*.csv, later files override earlier, *pass2*/*final* win (IFAN).
Rule (owner): unclear after checks counts as walk-ins welcome, kept as 'unconfirmed'
(card shows 'Walk-in not confirmed - call ahead'). Ids not in any file = unconfirmed.
Runs at the end of every refresh (scripts/build.py); re-run by hand after updating the CSVs."""
import csv, glob, json, os, sys
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def classify(r):
    c = (r.get('class') or '').strip().lower(); sub = (r.get('subclass') or '').lower()
    if c == 'voucher': return 'voucher'
    if c in ('walkin', 'self', 'self-referral', 'selfreferral') and 'assumed' not in sub: return 'walkin'
    return 'unconfirmed'

def main(root=ROOT):
    d = open(os.path.join(root, 'data.full.js'), encoding='utf-8').read()
    items = json.loads(d[d.index('{'):d.rindex('}') + 1])['items']
    files = sorted(glob.glob(os.path.join(root, 'overrides', 'access', 'voucher_split_*.csv')), key=lambda f: (('pass2' in f) or ('final' in f), f))
    m = {}
    for f in files:
        for r in csv.DictReader(open(f, encoding='utf-8')): m[r['id']] = classify(r)
    out = {i['id']: m.get(i['id'], 'unconfirmed') for i in items if i.get('kind') not in ('warehouse', 'dropoff')}
    tmp = os.path.join(root, 'access.js.tmp')
    open(tmp, 'w', encoding='utf-8').write('window.FB_ACCESS=' + json.dumps(out, separators=(',', ':')) + ';\n')
    os.replace(tmp, os.path.join(root, 'access.js'))
    print('access.js:', dict(Counter(out.values())), len(out), 'from', [os.path.basename(f) for f in files])
    return out

if __name__ == '__main__': main()
