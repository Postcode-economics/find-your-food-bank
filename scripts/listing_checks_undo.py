"""Undo the 28 Oct 2026 listing checks (logs/listing_checks_2026-10-28.json), one listing or all.
Usage: python scripts/listing_checks_undo.py <id> [<id> ...] | --all
Restores each override file entry to its value before the change (removes entries that did not exist before).
Then run the normal refresh (or build) so the map picks it up."""
import json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
LOG = os.path.join(ROOT, 'logs', 'listing_checks_2026-10-28.json')

def undo(ids=None, root=ROOT):
    log = json.load(open(os.path.join(root, 'logs', 'listing_checks_2026-10-28.json')))['changes']
    done = []
    for c in reversed(log):
        if ids is not None and c['key'] not in ids: continue
        fn, _, sub = c['file'].partition('#')
        p = os.path.join(root, 'overrides', fn); d = json.load(open(p, encoding='utf-8'))
        tgt = d.setdefault(sub, {}) if sub else d
        if c['before'] is None: tgt.pop(c['key'], None)
        else: tgt[c['key']] = c['before']
        open(p, 'w', encoding='utf-8').write(json.dumps(d, indent=1, ensure_ascii=False) + '\n')
        done.append((c['file'], c['key']))
    return done

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    for f, k in undo(None if a == ['--all'] else set(a)): print('undone', f, k)
