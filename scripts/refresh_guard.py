"""Refresh guard (Dean, 23 Oct 2026: 'it was absolutely essential we had all the information').
Run after a layer is rebuilt and before anything is committed. Compares the new file with the live one (git HEAD):
 - a place that vanished is put back with its previous record (unless deliberately removed: food bank exclusion /
   own-site closure lists, or overrides/guard_allow_remove.json),
 - a phone (phone/tel) that vanished is put back, and so is its venue label (phone_label),
 - a phone that stayed but lost its venue label gets that label back (same number only),
 - opening times (food banks: opening_times; shelters / warm spaces: hours) that vanished are put back.
Nothing is lost silently: every restore is listed in reports/refresh_guard_<layer>.md and logs/refresh_guard.json,
and (in CI, with GH_TOKEN) a 'refresh-alert' issue is opened. The restored file is published.
Food banks: a kept place also keeps its access.js tag (29 Oct: build.py had rebuilt access.js without the kept places).
The job fails, before anything is written, if a published food bank still has no access tag that it had before.
Usage: refresh_guard.py foodbanks|shelters|warmspaces [baseline-git-ref, default HEAD]"""
import datetime, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026: refresh stops if overrides/auto_apply_rules.json is missing
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FILES = {'foodbanks': 'data.full.js', 'shelters': 'shelters.js', 'warmspaces': 'warmspaces.js'}

def split(text):
    a, b = text.index('{'), text.rindex('}') + 1
    return text[:a], json.loads(text[a:b]), text[b:]

def load_json(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d

def wrong_times(layer):
    """Times proven wrong (e.g. a donation page's hours) may be dropped; the place and its phone always stay.
    overrides/guard_wrong_times.json {layer: {id: reason}} (24 Oct)."""
    return set(load_json('overrides/guard_wrong_times.json', {}).get(layer, {}))
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

_norm = lambda x: ''.join(c for c in (x or '').lower() if c.isalnum())

def moved_index(new_items):
    near = {}
    for i in new_items: near.setdefault(_norm(i.get('name')), []).append(i)
    return near

def moved_to(o, near):  # same place under a new id (sources re-key, e.g. IFAN): same name within ~300 m, or same name + postcode
    for i in near.get(_norm(o.get('name')), []):
        if i.get('id') == o.get('id'): continue
        try:
            if abs(float(i['lat']) - float(o['lat'])) < 0.003 and abs(float(i['lng']) - float(o['lng'])) < 0.005: return i
        except Exception: pass
        if o.get('postcode') and i.get('postcode') == o.get('postcode'): return i
    return None

def ws_not_restorable(run_day, root=None, closed_ids=()):
    """Warm spaces the build deliberately left out this run, which the guard must never put back (GB2 FAIL on #235, 28 Oct):
    carry_forward's not_carried list for this run (season ended, closed, excluded, allowed removal, moved), every id in
    overrides/warmspaces_exclude.json, and anything in this run's recently_closed."""
    import carry_forward as CF
    root = root or ROOT
    lg = load_json(os.path.join(root, 'logs', 'warmspaces_carry_forward.json'), {})
    # Same run, not same date (GB2, 28 Oct): a refresh that crosses midnight UTC wrote the log with yesterday's date.
    # Match on the workflow run id when both sides have one; otherwise fall back to the run day.
    rid = CF.run_id()
    same = (lg.get('run_id') == rid) if (rid and lg.get('run_id')) else (lg.get('run') == run_day)
    nc = {r['id']: r.get('why', 'not_carried') for r in lg.get('not_carried', [])} if same else {}
    for i in CF.excluded_ids(root): nc.setdefault(i, 'excluded')
    for i in closed_ids: nc.setdefault(i, 'closed')
    return nc

def guard(layer, old_items, new_items, run_day=None, closed_ids=(), root=None):
    ok, ex = allowed_removals(layer)
    run_day = run_day or datetime.date.today().isoformat()
    if layer == 'warmspaces':
        import carry_forward as CF
        skip_ws = ws_not_restorable(run_day, root, closed_ids)
        pend = {p['id']: p for p in load_json(os.path.join(root or ROOT, 'logs', 'warmspaces_pending.json'), []) if isinstance(p, dict) and p.get('id')}
        conf = load_json(os.path.join(root or ROOT, 'logs', 'warmspaces_last_confirmed.json'), {})
    new = {i['id']: i for i in new_items}
    mv = moved_index(new_items)
    moved = lambda o: moved_to(o, mv) is not None
    out = list(new_items); rep = {'places': [], 'phones': [], 'times': []}
    for o in old_items:
        n = new.get(o['id'])
        if n is None:
            if removal_ok(o, ok, ex) or moved(o): continue
            if layer == 'warmspaces':  # never undo the build's deliberate drops; a restored venue gets carry-forward's label + link check
                why = skip_ws.get(o['id']) or CF.why_not(o, run_day, valid_until=CF.season_end)
                if why: rep.setdefault('not_restored', []).append({'id': o['id'], 'why': why}); continue
                out.append(dict(CF.label(o, run_day, pend, conf), guard_kept=run_day)); rep['places'].append(o['id']); continue
            out.append(dict(o, guard_kept=datetime.date.today().isoformat())); rep['places'].append(o['id']); continue
        had, has = o.get('tel') or o.get('phone'), n.get('tel') or n.get('phone')
        if had and not has and 'phone_was' not in n and o['id'] not in ok:  # phone_was = deliberate drop_phone override
            for k in ('phone', 'tel', 'phone_source'):
                if o.get(k): n[k] = o[k]
            if o.get('phone_label'): n['phone_label'] = o['phone_label']  # rule 21: the venue label belongs with the number
            rep['phones'].append(o['id'])
        elif had and has and 'phone_was' not in n and o['id'] not in ok and o.get('phone_label') and not str(n.get('phone_label') or '').strip():
            od = ''.join(c for c in str(had) if c.isdigit()); nd = ''.join(c for c in str(has) if c.isdigit())
            if od and od == nd:  # same number, label stripped: put the venue label back. A different number keeps no old label.
                n['phone_label'] = o['phone_label']; rep.setdefault('phone_labels', []).append(o['id'])
        if has_times(layer, o) and not has_times(layer, n) and o['id'] not in ok and o['id'] not in wrong_times(layer):
            for k in (('opening_times',) if layer == 'foodbanks' else ('hours', 'hours_source', 'hours_checked')):
                if k in o: n[k] = o[k]
            rep['times'].append(o['id'])
        if layer == 'foodbanks' and o.get('fb_page') and not n.get('fb_page'):  # verified Facebook page never silently lost (24 Oct)
            n['fb_page'] = o['fb_page']; rep.setdefault('fb_pages', []).append(o['id'])
        if layer == 'shelters' and o.get('groups') and not n.get('groups'):  # who it's for never lost (Dean, 23 Oct)
            n['groups'] = o['groups']
            if o.get('groups_source'): n['groups_source'] = o['groups_source']
            rep.setdefault('groups', []).append(o['id'])
    return out, rep

ACCESS = 'access.js'
NO_TAG = ('warehouse', 'dropoff')  # build_access.py never tags these

def write_access(acc, root=None):
    p = os.path.join(root or ROOT, ACCESS); t = p + '.tmp'
    open(t, 'w', encoding='utf-8').write('window.FB_ACCESS=' + json.dumps(acc, separators=(',', ':')) + ';\n'); os.replace(t, p)

def carry_access(kept, old_acc, acc):
    """build.py rebuilds access.js only from the places it built (full_check.py then applies its flips), so a place the
    guard kept has no filter-chip tag. Give it back the tag it had in the published access.js."""
    back = [k for k in kept if k in old_acc and k not in acc]
    for k in back: acc[k] = old_acc[k]
    return back

def lost_access(items, old_acc, acc):
    """Published places that had an access tag before and have none now."""
    return [i['id'] for i in items if i['id'] in old_acc and i['id'] not in acc and i.get('kind') not in NO_TAG]

def main(layer, ref='HEAD'):
    f = os.path.join(ROOT, FILES[layer])
    try: old_txt = subprocess.check_output(['git', 'show', f'{ref}:{FILES[layer]}'], cwd=ROOT, text=True)
    except Exception: print('guard: no baseline, skipped'); return {}
    _, old, _ = split(old_txt); pre, cur, post = split(open(f).read())
    items, rep = guard(layer, old['items'], cur['items'], closed_ids=[x['id'] for x in cur.get('recently_closed', []) if isinstance(x, dict) and 'id' in x])
    if layer == 'foodbanks':
        try: _, old_acc, _ = split(subprocess.check_output(['git', 'show', f'{ref}:{ACCESS}'], cwd=ROOT, text=True))
        except Exception: old_acc = {}
        _, acc, _ = split(open(os.path.join(ROOT, ACCESS), encoding='utf-8').read())
        back = carry_access(rep['places'], old_acc, acc)
        if back: write_access(acc); rep['access'] = back
        lost = lost_access(items, old_acc, acc)
        if lost:
            print(f'::error::refresh guard: {len(lost)} published food banks lost their access tag (access.js): ' + ', '.join(lost))
            sys.exit(1)
    n = sum(len(v) for k, v in rep.items() if k != 'not_restored')
    summ = f"{layer}: kept {len(rep['places'])} places, {len(rep['phones'])} phones, {len(rep['times'])} opening times that this run would have dropped" + (f"; {len(rep['not_restored'])} left out on purpose by the build were not restored" if rep.get('not_restored') else '')
    print('refresh guard:', summ)
    lg = load_json('logs/refresh_guard.json', {}); lg[layer] = dict(when=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), **rep)
    json.dump(lg, open(os.path.join(ROOT, 'logs', 'refresh_guard.json'), 'w'), indent=1)
    md = [f'# Refresh guard: {layer} ({lg[layer]["when"]})', '', summ + '. Previous values were kept and published; please check why the source lost them.', '']
    for k, v in rep.items():
        if v and k == 'not_restored': md += [f'## Not restored: left out on purpose by the build ({len(v)})', ''] + [f"- {x['id']}: {x['why']}" for x in v] + ['']
        elif v: md += [f'## {k} kept ({len(v)})', ''] + [f'- {x}' for x in v] + ['']
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
