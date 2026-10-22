"""One-off/occasional: build outcodes.json, the offline fallback for postcode search (used only when api.postcodes.io fails).
Outcode list: Gibbs/UK-Postcodes (CC0); centroids re-fetched from api.postcodes.io /outcodes (ONS Postcode Directory, OGL).
Format: {"OUTCODE":[lat,lng],...} at 4dp (~10 m). Stdlib only."""
import concurrent.futures as cf, csv, io, json, os, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = 'https://raw.githubusercontent.com/Gibbs/UK-Postcodes/master/postcodes.csv'
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'helpmap.uk outcode table'}), timeout=20) as r: return r.read().decode()
def one(row):
    oc = row['postcode'].strip().upper()
    try:
        r = json.loads(get('https://api.postcodes.io/outcodes/' + oc))['result']
        if r and r.get('latitude'): return oc, [round(r['latitude'], 4), round(r['longitude'], 4)]
    except Exception: pass
    try: return oc, [round(float(row['latitude']), 4), round(float(row['longitude']), 4)]
    except Exception: return oc, None
rows = list(csv.DictReader(io.StringIO(get(SRC))))
with cf.ThreadPoolExecutor(4) as ex: out = dict(x for x in ex.map(one, rows) if x[1])
json.dump(dict(sorted(out.items())), open(os.path.join(ROOT, 'outcodes.json'), 'w'), separators=(',', ':'))
print(len(out), 'outcodes')
