"""Carry-forward (Dean, 28 Oct 2026: remove nothing; label doubtful places 'call before you go').
A warm space published last run but missing this run (left the feed, or not re-confirmed) is carried forward from
the previous warmspaces.js with call_check=True and the note 'Not re-confirmed since <carried_since> – call before
you go', and listed in logs/warmspaces_carry_forward.json + reports/warmspaces_carry_forward.md. Never deleted.
After REVIEW_DAYS carried it is flagged for Dean's review (review: true in the log, 'For review' section in the report).
Not carried (deliberate or pre-existing removals, so the verification gate's season logic is never bypassed):
  - overrides/warmspaces_exclude.json, overrides/guard_allow_remove.json['warmspaces'], places closed this run
    (recently_closed / flag_closed / own-site closed / seasonal expired);
  - past the season its last verification was valid for (season_end, to 30 April), or past its own scheme end date;
  - venues that moved to a new id this run (refresh_guard.moved_to), so nothing is listed twice.
A venue whose source page now redirects to a different site is carried WITHOUT the website link, and flagged.
The label date is the venue's last confirmation (last_confirmed / last_verified / verified_on), not the day carrying began.
refresh_guard.py uses the same rules (not_restorable + label) for warm spaces, so the guard can never put back a venue
this module deliberately left out, and anything it does restore is labelled and link-stripped the same way."""
import datetime, json, os
import refresh_guard

REVIEW_DAYS = 14
NOTE = 'Not re-confirmed since %s – call before you go'

def host(u):
    return (u or '').split('//')[-1].split('/')[0].split(':')[0].lower().removeprefix('www.')

def redirected_off_site(rec):
    """rec: a pending entry's 'recheck' dict (url, final_url). True if the final URL is on a different domain."""
    rec = rec or {}
    a, b = host(rec.get('url')), host(rec.get('final_url'))
    return bool(a and b and a != b)

def days_between(a, b):
    try: return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days
    except Exception: return 0

def season_end(v):  # same rule as build_warmspaces.season_end: a verification is valid only to the end of its winter season (30 April)
    d = datetime.date.fromisoformat((v.get('verified_on') or '2000-01-01')[:10])
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"

def load_json(p, d):
    try: return json.load(open(p))
    except Exception: return d

def excluded_ids(root='.'):
    return {e['id'] for e in load_json(os.path.join(root, 'overrides', 'warmspaces_exclude.json'), []) if isinstance(e, dict) and e.get('id')}

def last_confirmed(o, confirmed=None):
    d = (confirmed or {}).get(o['id']) or o.get('last_confirmed') or o.get('last_verified') or o.get('verified_on') or o.get('first_verified_on') or ''
    return d[:10] if len(d) >= 10 and d[4] == '-' else ''

def label(o, run_day, pending=None, confirmed=None):
    """The carried / restored copy of a previous venue: call_check, 'Not re-confirmed since <last confirmed>' note,
    website removed if its page now redirects to another site, review flag after REVIEW_DAYS or on a redirect."""
    x = dict(o); x['call_check'] = True; x['stale'] = False
    x.setdefault('carried_since', run_day); x['carried_forward'] = run_day
    if not x.get('last_confirmed'):
        lc = last_confirmed(o, confirmed)
        if lc: x['last_confirmed'] = lc
    x['carried_note'] = NOTE % (x.get('last_confirmed') or x['carried_since'])
    p = (pending or {}).get(o['id'])
    if p and redirected_off_site(p.get('recheck')):
        x['website_dropped'] = x.pop('website', '') or (p['recheck'] or {}).get('url', '')
        x['website_redirects_to'] = host(p['recheck'].get('final_url'))
        x.pop('url', None)
    x['carried_days'] = days_between(x['carried_since'], run_day)
    x['review'] = x['carried_days'] >= REVIEW_DAYS or bool(x.get('website_redirects_to'))
    return x

def why_not(o, run_day, excluded=(), allowed=(), skip=(), valid_until=season_end):
    """Reason a previous venue must NOT be carried/restored this run, or None."""
    if o['id'] in excluded: return 'excluded'
    if o['id'] in allowed: return 'guard_allow_remove'
    if o['id'] in skip or o.get('flag_closed'): return 'closed'
    if not season_ok(o, run_day, valid_until): return 'season_ended'
    return None

def season_ok(o, run_day, valid_until):
    """Same season rule as the verification gate: a verification is valid only to the end of its winter season."""
    if o.get('ended'): return False
    se = o.get('scheme_end') or ''
    if len(se) == 10 and se[4] == '-' and se < run_day: return False
    if valid_until:
        d = o.get('verified_on') or o.get('last_verified') or o.get('first_verified_on')
        if d and run_day > valid_until({'verified_on': d[:10]}): return False
    return True

def carry_items(prev_items, items, closed, run_day, excluded=(), allowed=None, skip=(), pending=None, valid_until=None, confirmed=None):
    """Returns (items, carried, not_carried). prev_items: last published items. items/closed: this run's output.
    skip: ids removed on purpose this run (own-site closed, seasonal expired). pending: verification gate's pending list."""
    if allowed is None: allowed = refresh_guard.allowed_removals('warmspaces')[0]
    have = {x['id'] for x in items} | {x['id'] for x in closed}
    pend = {p['id']: p for p in (pending or [])}
    near = refresh_guard.moved_index(list(items))
    carried, not_carried = [], []
    for o in prev_items or []:
        if o['id'] in have: continue
        why = why_not(o, run_day, excluded, allowed, skip, valid_until)
        if not why:
            m = refresh_guard.moved_to(o, near)
            if m: why = 'moved_to:' + m['id']
        if why:
            not_carried.append({'id': o['id'], 'name': o.get('name', ''), 'why': why}); continue
        x = label(o, run_day, pend, confirmed)
        carried.append(x); have.add(x['id'])
    out = sorted(list(items) + carried, key=lambda x: x['name'].lower())
    return out, carried, not_carried

def write_log(carried, run_day, root='.', layer='warmspaces', not_carried=()):
    rows = [{'id': x['id'], 'name': x['name'], 'postcode': x.get('postcode', ''), 'carried_since': x.get('carried_since', run_day), 'last_confirmed': x.get('last_confirmed', ''),
             'carried_days': x.get('carried_days', 0), 'review': bool(x.get('review')), 'note': x.get('carried_note', ''),
             **({'website_dropped': x['website_dropped'], 'redirects_to': x['website_redirects_to']} if x.get('website_redirects_to') else {}),
             'reason': 'missing from this run (left the feed or not re-confirmed); kept with call before you go'} for x in carried]
    os.makedirs(os.path.join(root, 'logs'), exist_ok=True); os.makedirs(os.path.join(root, 'reports'), exist_ok=True)
    json.dump({'run': run_day, 'review_after_days': REVIEW_DAYS, 'carried': rows, 'not_carried': list(not_carried)},
              open(os.path.join(root, 'logs', f'{layer}_carry_forward.json'), 'w'), indent=1, ensure_ascii=False)
    line = lambda r: (f"- {r['name']} ({r['id']}, {r['postcode']}), last confirmed {r['last_confirmed'] or 'unknown'}, carried since {r['carried_since']} ({r['carried_days']} days)"
                      + (f"; website link removed, it now redirects to {r['redirects_to']}" if r.get('redirects_to') else ''))
    rev = [r for r in rows if r['review']]
    md = [f'# {layer}: carried forward ({run_day})', '',
          'Missing from this run, so kept from the previous file and labelled "Not re-confirmed since <date> – call before you go". Nothing is deleted.', '',
          f'## For review (carried {REVIEW_DAYS}+ days, or website now redirects elsewhere)', '']
    md += [line(r) for r in rev] or ['None.']
    md += ['', '## Carried', ''] + ([line(r) for r in rows] or ['None this run.'])
    if not_carried:
        md += ['', '## Not carried (removed on purpose, season ended, or moved to a new id)', ''] + [f"- {r['name']} ({r['id']}): {r['why']}" for r in not_carried]
    open(os.path.join(root, 'reports', f'{layer}_carry_forward.md'), 'w').write('\n'.join(md) + '\n')
    return rows
