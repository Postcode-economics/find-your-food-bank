"""Carry-forward (Dean, 28 Oct 2026: remove nothing; label doubtful places 'call before you go').
A warm space that was published last run but is missing from this run (left the feed, or not re-confirmed) is
carried forward from the previous warmspaces.js with call_check=True ('Times unknown - call before you go') and
listed in logs/warmspaces_carry_forward.json + reports/warmspaces_carry_forward.md for review. Never deleted.
Same rule as scripts/refresh_guard.py (which restores in the workflow after the build); this does it at the root,
inside the build, so a standalone build_warmspaces.py run cannot drop a venue either.
Skipped (deliberate removals only): overrides/warmspaces_exclude.json, overrides/guard_allow_remove.json
['warmspaces'], and places closed on purpose (flag_closed) that are already in recently_closed."""
import datetime, json, os
import refresh_guard

def carry_items(prev_items, items, closed, run_day, excluded=(), allowed=None):
    """Returns (items, carried). prev_items: last published items. items/closed: this run's output."""
    if allowed is None: allowed = refresh_guard.allowed_removals('warmspaces')[0]
    have = {x['id'] for x in items} | {x['id'] for x in closed}
    carried = []
    for o in prev_items or []:
        if o['id'] in have or o['id'] in excluded or o['id'] in allowed: continue
        x = dict(o); x['call_check'] = True; x['stale'] = False
        x.setdefault('carried_since', run_day); x['carried_forward'] = run_day
        carried.append(x); have.add(x['id'])
    out = sorted(list(items) + carried, key=lambda x: x['name'].lower())
    return out, carried

def write_log(carried, run_day, root='.', layer='warmspaces'):
    rows = [{'id': x['id'], 'name': x['name'], 'postcode': x.get('postcode', ''), 'carried_since': x.get('carried_since', run_day),
             'reason': 'missing from this run (left the feed or not re-confirmed); kept with call before you go'} for x in carried]
    os.makedirs(os.path.join(root, 'logs'), exist_ok=True); os.makedirs(os.path.join(root, 'reports'), exist_ok=True)
    json.dump({'run': run_day, 'carried': rows}, open(os.path.join(root, 'logs', f'{layer}_carry_forward.json'), 'w'), indent=1, ensure_ascii=False)
    md = [f'# {layer}: carried forward ({run_day})', '', 'Missing from this run, so kept from the previous file and labelled "call before you go". Please check each one.', '']
    md += [f"- {r['name']} ({r['id']}, {r['postcode']}), carried since {r['carried_since']}" for r in rows] or ['None this run.']
    open(os.path.join(root, 'reports', f'{layer}_carry_forward.md'), 'w').write('\n'.join(md) + '\n')
    return rows
