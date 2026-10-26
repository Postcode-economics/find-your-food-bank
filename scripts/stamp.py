"""Write stamp.js: the UK date+time of this refresh/sweep run. The footer's 'last updated' and
'checked' read it, so every 3x-daily refresh and overnight sweep bakes in its own run time.
layers: {fb|sh|ws: {run,label}} = each layer's own last published refresh (kept across runs).
Usage: stamp.py write <kind> | stamp.py verify | stamp.py combine-index
  verify fails loudly if the stamp is not from this run.
  combine-index merges the two sides of a rebase conflict, keeping the later date of each layer.
  (26 Oct: `git pull --rebase -X theirs` kept one refresh's whole stamp.js and wiped the other layers.)"""
import datetime, json, os, subprocess, sys
from zoneinfo import ZoneInfo
P = os.path.join(os.path.dirname(__file__), '..', 'stamp.js')

def _when(layer):
    try: return datetime.datetime.fromisoformat((layer or {}).get('run') or '')
    except Exception: return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

def combine(a, b):
    """Later run wins for each layer. The header stamp is whichever side ran later."""
    a, b = a or {}, b or {}
    layers = {}
    for k in set((a.get('layers') or {})) | set((b.get('layers') or {})):
        la = (a.get('layers') or {}).get(k) or {}
        lb = (b.get('layers') or {}).get(k) or {}
        layers[k] = la if _when(la) >= _when(lb) else lb
    top = a if _when(a) >= _when(b) else b
    out = dict(top)
    out['layers'] = layers
    return out

def _load_text(text):
    return json.loads(text.split('=', 1)[1].rstrip().rstrip(';'))

def combine_index():
    """Rebase conflict: stage 2 is the upstream stamp, stage 3 is this run's stamp."""
    sides = []
    for n in (2, 3):
        r = subprocess.run(['git', 'show', ':%d:stamp.js' % n], capture_output=True, text=True)
        sides.append(_load_text(r.stdout) if r.returncode == 0 and r.stdout.strip() else {})
    open(P, 'w').write('window.FB_STAMP=' + json.dumps(combine(*sides)) + ';\n')
    print('stamp combined', combine(*sides).get('label'))

def main():
    now = datetime.datetime.now(ZoneInfo('Europe/London'))
    if sys.argv[1] == 'write':
        s = dict(run=now.isoformat(timespec='seconds'), kind=sys.argv[2] if len(sys.argv) > 2 else 'refresh',
                 label=f"{now.day} {now:%b %Y}, {now:%H:%M}")  # owner 25 Oct: one format "25 Oct 2026, 05:12"
        try: prev = json.loads(open(P).read().split('=', 1)[1].rstrip().rstrip(';'))
        except Exception: prev = {}
        layers = dict(prev.get('layers') or {})  # owner 25 Oct: each layer keeps its own last refresh (key + footer dates)
        k = {'refresh': 'fb', 'shelters': 'sh', 'warmspaces': 'ws'}.get(s['kind'])
        if k: layers[k] = dict(run=s['run'], label=s['label'])
        s['layers'] = layers
        open(P, 'w').write('window.FB_STAMP=' + json.dumps(s) + ';\n'); print('stamped', s['label'])
    elif sys.argv[1] == 'combine-index':
        combine_index()
    else:
        s = json.loads(open(P).read().split('=', 1)[1].rstrip().rstrip(';'))
        age = (now - datetime.datetime.fromisoformat(s['run'])).total_seconds()
        if not 0 <= age < 900: sys.exit(f"::error::stamp.js not updated by this run (stamp {s['run']}, age {age:.0f}s)")
        print('stamp ok', s['label'])
if __name__ == '__main__':
    main()
