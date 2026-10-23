"""Refresh guard (Dean, 23 Oct 2026: 'it was absolutely essential we had all the information').
Run after a layer is rebuilt and before anything is committed. Compares the new file with the live one (git HEAD):
 - a place that vanished is put back with its previous record (unless deliberately removed: food bank exclusion /
   own-site closure lists, or overrides/guard_allow_remove.json),
 - a phone (phone/tel) that vanished is put back,
 - opening times (food banks: opening_times; shelters / warm spaces: hours) that vanished are put back.
Nothing is lost silently: every restore is listed in reports/refresh_guard_<layer>.md and logs/refresh_guard.json,
and (in CI, with GH_TOKEN) a 'refresh-alert' issue is opened. Never fails the job; the restored file is published.
Usage: refresh_guard.py foodbanks|shelters|warmspaces [baseline-git-ref, default HEAD]"""
import datetime, json, os, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FILES = {'foodbanks': 'data.full.js', 'shelters': 'shelters.js', 'warmspaces': 'warmspaces.js'}

def split(text):
    a, b = text.index('{'), text.rindex('}') + 1
    return text[:a], json.loads(text[a:b]), text[b:]

def load_json(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d

def allowed_removals(layer):
    ok = set(load_json('overrides/guard_allow_remove.json', {}).get(layer, []))
    if layer == 'foodbanks':
        ok |= {k for k in load_json('overrides/foodbank_closed.json', {}) if not k.startswith('_')}
        ex = load_json('overrides/foodbank_exclude.json', {}).get('foodbanks', [])
        return ok, ex
    return ok, []

def removal_ok(i, ok, ex):
    if i['id'] in ok or i['id'].split('/')[0] in ok: return True
    host = (i.get('website') or '').split('//')[-1].split('/')[0].lower().removeprefix('www.')
    return any(i['id'] == e['slug'] or (not e.get('exact') and (i['id'].startswith(e['slug'] + '/') or (e.get('host') and host == e['host']))) for e in ex)

def has_times(layer, i):
    if layer == 'foodbanks':
        ot = i.get('opening_times') or {}
        return bool(ot.get('raw') or ot.get('structured') or ot.get('text') or ot.get('sessions'))
    return bool(i.get('hours'))

def guard(layer, old_items, new_items):
    ok, ex = allowed_removals(layer)
    new = {i['id']: i for i in new_items}
    norm = lambda x: ''.join(c for c in (x or '').lower() if c.isalnum())
    near = {}
    for i in new_items: near.setdefault(norm(i.get('name')), []).append(i)
    def moved(o):  # same place under a new id (sources re-key, e.g. IFAN): same name within ~300 m, or same name + postcode
        for i in near.get(norm(o.get('name')), []):
            try:
                if abs(float(i['lat']) - float(o['lat'])) < 0.003 and abs(float(i['lng']) - float(o['lng'])) < 0.005: return True
            except Exception: pass
            if o.get('postcode') and i.get('postcode') == o.get('postcode'): return True
        return False
    out = list(new_items); rep = {'places': [], 'phones': [], 'times': []}
    for o in old_items:
        n = new.get(o['id'])
        if n is None:
            if removal_ok(o, ok, ex) or moved(o): continue
            out.append(dict(o, guard_kept=datetime.date.today().isoformat())); rep['places'].append(o['id']); continue
        if (o.get('tel') or o.get('phone')) and not (n.get('tel') or n.get('phone')) and 'phone_was' not in n and o['id'] not in ok:  # phone_was = deliberate drop_phone override
            for k in ('phone', 'tel', 'phone_source'):
                if o.get(k): n[k] = o[k]
            rep['phones'].append(o['id'])
        if has_times(layer, o) and not has_times(layer, n) and o['id'] not in ok:
            for k in (('opening_times',) if layer == 'foodbanks' else ('hours', 'hours_source', 'hours_checked')):
                if k in o: n[k] = o[k]
            rep['times'].append(o['id'])
        if layer == 'shelters' and o.get('groups') and not n.get('groups'):  # who it's for never lost (Dean, 23 Oct)
            n['groups'] = o['groups']
            if o.get('groups_source'): n['groups_source'] = o['groups_source']
            rep.setdefault('groups', []).append(o['id'])
    return out, rep

def main(layer, ref='HEAD'):
    f = os.path.join(ROOT, FILES[layer])
    try: old_txt = subprocess.check_output(['git', 'show', f'{ref}:{FILES[layer]}'], cwd=ROOT, text=True)
    except Exception: print('guard: no baseline, skipped'); return {}
    _, old, _ = split(old_txt); pre, cur, post = split(open(f).read())
    items, rep = guard(layer, old['items'], cur['items'])
    n = sum(len(v) for v in rep.values())
    summ = f"{layer}: kept {len(rep['places'])} places, {len(rep['phones'])} phones, {len(rep['times'])} opening times that this run would have dropped"
    print('refresh guard:', summ)
    lg = load_json('logs/refresh_guard.json', {}); lg[layer] = dict(when=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), **rep)
    json.dump(lg, open(os.path.join(ROOT, 'logs', 'refresh_guard.json'), 'w'), indent=1)
    md = [f'# Refresh guard: {layer} ({lg[layer]["when"]})', '', summ + '. Previous values were kept and published; please check why the source lost them.', '']
    for k, v in rep.items():
        if v: md += [f'## {k} kept ({len(v)})', ''] + [f'- {x}' for x in v] + ['']
    open(os.path.join(ROOT, 'reports', f'refresh_guard_{layer}.md'), 'w').write('\n'.join(md))
    if n:
        cur['items'] = items
        fb = layer == 'foodbanks'  # same serialisation as the builders (build.py: json.dumps defaults)
        open(f, 'w').write(pre + (json.dumps(cur) if fb else json.dumps(cur, ensure_ascii=False, separators=(',', ':'))) + post)
        if os.environ.get('GH_TOKEN'):
            subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'alert.py'), 'open', f'guard-{layer}', f'Refresh would have dropped data ({layer})',
                            summ + '. Previous values kept. Details: reports/refresh_guard_' + layer + '.md'])
    return rep

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'HEAD')
