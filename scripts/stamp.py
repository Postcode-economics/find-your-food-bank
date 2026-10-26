"""Write stamp.js: the UK date+time of this refresh. The footer's 'last updated' and the
map key read each layer's own time. A phone-and-opening-times check has its own time.

layers live in stamps/{fb,sh,ws}.json, one file per refresh, so two refreshes running
together cannot wipe each other's time. A rebase conflict in stamp.js is merged by
combine-index (the later time of each layer, and of the phone check). assemble then
rebuilds stamp.js from those files, keeping the newer time. A sweep is not a layer
refresh and does not move any date the site shows. The check time is written only by
a real check (stamp.py write check), never copied from the food bank publish time.

Usage: stamp.py write <refresh|shelters|warmspaces|sweep|check> | stamp.py assemble | stamp.py combine-index | stamp.py verify
"""
import datetime, json, os, subprocess, sys
from zoneinfo import ZoneInfo
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
P = os.path.join(ROOT, 'stamp.js')
DIR = os.path.join(ROOT, 'stamps')
LAYER = {'refresh': 'fb', 'shelters': 'sh', 'warmspaces': 'ws'}
KIND = {'fb': 'refresh', 'sh': 'shelters', 'ws': 'warmspaces'}
ORDER = ('fb', 'sh', 'ws')

def lab(now):
    return f"{now.day} {now:%b %Y}, {now:%H:%M}"  # Dean 25 Oct: one format "25 Oct 2026, 05:12"

def _dt(rec):
    if not rec or not rec.get('run'): return None
    try: return datetime.datetime.fromisoformat(rec['run'])
    except Exception: return None

def _when(layer):
    try: return datetime.datetime.fromisoformat((layer or {}).get('run') or '')
    except Exception: return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

def newer(a, b):
    """The later of two {run, label} records. Equal times keep a. Missing records lose."""
    da, db = _dt(a), _dt(b)
    if da is None: return b
    if db is None: return a
    return a if da >= db else b

def combine(a, b):
    """Later run wins for each layer and for the phone check. The header is whichever side ran later."""
    a, b = a or {}, b or {}
    layers = {}
    for k in set((a.get('layers') or {})) | set((b.get('layers') or {})):
        la = (a.get('layers') or {}).get(k) or {}
        lb = (b.get('layers') or {}).get(k) or {}
        layers[k] = la if _when(la) >= _when(lb) else lb
    top = a if _when(a) >= _when(b) else b
    out = dict(top)
    out['layers'] = layers
    ca, cb = a.get('checked') or {}, b.get('checked') or {}
    if ca or cb:
        out['checked'] = ca if _when(ca) >= _when(cb) else cb
    return out

def _load_text(text):
    return json.loads(text.split('=', 1)[1].rstrip().rstrip(';'))

def combine_index():
    """Rebase conflict: stage 2 is the upstream stamp, stage 3 is this run's stamp."""
    sides = []
    for n in (2, 3):
        r = subprocess.run(['git', 'show', ':%d:stamp.js' % n], capture_output=True, text=True)
        sides.append(_load_text(r.stdout) if r.returncode == 0 and r.stdout.strip() else {})
    merged = combine(*sides)
    open(P, 'w').write('window.FB_STAMP=' + json.dumps(merged) + ';\n')
    print('stamp combined', merged.get('label'))

def read_json(path):
    try: return json.loads(open(path, encoding='utf-8').read())
    except Exception: return None

def read_stamp(path=P):
    try: return json.loads(open(path, encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    except Exception: return {}

def _dump(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and open(path, encoding='utf-8').read() == text: return
    open(path, 'w', encoding='utf-8').write(text)

def _piece(rec):
    if not rec or not rec.get('run') or not rec.get('label'): return None
    return {'run': rec['run'], 'label': rec['label']}

def _keep_file(folder, name, won, had_file):
    """Update a file only when it already exists and stamp.js is newer. Never create another layer's file:
    a concurrent refresh commits only its own file, so a rebase cannot replace that file with a stale copy."""
    if not won or not had_file: return
    _dump(os.path.join(folder, name), json.dumps(won) + '\n')

def assemble(path=P):
    """Rebuild stamp.js from the per-layer files and whatever is already in stamp.js, keeping the newer time for each."""
    prev = read_stamp(path)
    root = os.path.dirname(os.path.abspath(path))
    folder = os.path.join(root, 'stamps')
    layers = {}
    for k in ORDER:
        fp = os.path.join(folder, k + '.json')
        had = os.path.exists(fp)
        won = _piece(newer(read_json(fp), (prev.get('layers') or {}).get(k)))
        if won:
            layers[k] = won
            _keep_file(folder, k + '.json', won, had)
    cpath = os.path.join(folder, 'checked.json')
    had_c = os.path.exists(cpath)
    checked = _piece(newer(read_json(cpath), prev.get('checked')))
    _keep_file(folder, 'checked.json', checked, had_c)
    best_k = max(layers, key=lambda k: _dt(layers[k])) if layers else None
    if best_k:
        run, label, kind = layers[best_k]['run'], layers[best_k]['label'], KIND[best_k]
    else:
        run, label, kind = prev.get('run'), prev.get('label'), prev.get('kind') or 'refresh'
    s = {'run': run, 'kind': kind, 'label': label, 'layers': layers}
    if checked: s['checked'] = checked
    _dump(path, 'window.FB_STAMP=' + json.dumps(s) + ';\n')
    return s

def record(kind, now=None):
    """Stamp one thing. kind refresh/shelters/warmspaces/check moves that date. sweep is recorded and shown nowhere."""
    now = now or datetime.datetime.now(ZoneInfo('Europe/London'))
    rec = {'run': now.isoformat(timespec='seconds'), 'label': lab(now)}
    os.makedirs(DIR, exist_ok=True)
    if kind == 'check': name = 'checked.json'
    elif kind == 'sweep': name = 'sweep.json'
    elif kind in LAYER: name = LAYER[kind] + '.json'
    else: sys.exit('unknown stamp kind ' + str(kind))
    _dump(os.path.join(DIR, name), json.dumps(rec) + '\n')
    s = assemble()
    print('stamped', kind, rec['label'])
    return s

def verify():
    now = datetime.datetime.now(ZoneInfo('Europe/London'))
    s = read_stamp()
    cands = [s.get('run')]
    cands += [v.get('run') for v in (s.get('layers') or {}).values()]
    if s.get('checked'): cands.append(s['checked'].get('run'))
    sw = read_json(os.path.join(DIR, 'sweep.json'))
    if sw: cands.append(sw.get('run'))
    for c in cands:
        d = _dt({'run': c}) if c else None
        if d is None: continue
        age = (now - d).total_seconds()
        if 0 <= age < 900:
            print('stamp ok', s.get('label')); return
    sys.exit(f"::error::stamp.js not updated by this run (stamp {s.get('run')})")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'write': record(sys.argv[2] if len(sys.argv) > 2 else 'refresh')
    elif cmd == 'assemble':
        s = assemble(); print('assembled', s.get('label'))
    elif cmd == 'combine-index': combine_index()
    elif cmd == 'verify': verify()
    else: sys.exit('usage: stamp.py write <kind> | assemble | combine-index | verify')

if __name__ == '__main__':
    main()
