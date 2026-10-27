"""Publish gate (Dean, 23 Oct 2026). Runs in every shelters / warm spaces / food bank refresh, before the refresh guard.
gate <layer>: a NEW place (not in the live file, git HEAD) is not published unless it has a verified phone
  (own number 'tel'; for shelters / warm spaces a labelled council homeless/out-of-hours line also counts) and,
  for shelters, a sourced 'who it's for' (groups). Held places go to logs/pending_dean.json + reports/pending_dean.md.
  Existing places are never removed here (the refresh guard keeps their fields).
check: CI. Fails if a published shelter lacks a phone or groups, or a warm space lacks a phone, unless the id is
  listed in overrides/known_gaps.json (existing gaps being worked on, each with a note). Food banks without a
  phone are reported only (count printed), never failing, so the live map is not blocked."""
import datetime, json, os, re, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FILES = {'foodbanks': 'data.full.js', 'shelters': 'shelters.js', 'warmspaces': 'warmspaces.js'}
def split(t): a, b = t.index('{'), t.rindex('}') + 1; return t[:a], json.loads(t[a:b]), t[b:]
def has_phone(layer, i):
    if i.get('tel'): return True
    if layer == 'warmspaces': return bool(i.get('council_label') and i.get('council_phone'))  # verified council out-of-hours homeless line only; general council lines are a gap
    return layer == 'shelters' and bool(i.get('council_ooh') or i.get('council_phone'))
def problems(layer, i):
    p = [] if has_phone(layer, i) else ['no verified phone']
    if layer == 'shelters' and not i.get('groups'): p.append("no sourced 'who it's for'")
    return p
def load(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026
def approved_new():
    """Dean 25 Oct 08:20: no new food bank is auto-added. Only ids Dean OK'd (overrides/foodbank_approved_new.json) or
    hand-added (overrides/foodbank_added.json) may go on the map; everything else waits in reports/pending_dean.md."""
    ok = set()
    for f in ('overrides/foodbank_approved_new.json', 'overrides/foodbank_added.json'):
        ok |= {k for k in load(f, {}) if not k.startswith('_')}
    return ok
def gate(layer, ref='HEAD'):
    f = os.path.join(ROOT, FILES[layer])
    try: live = {i['id'] for i in split(subprocess.check_output(['git', 'show', f'{ref}:{FILES[layer]}'], cwd=ROOT, text=True))[1]['items']}
    except Exception: print('gate: no live baseline, skipped'); return []
    import override_check
    ok_files, why = override_check.assess(ROOT)
    if not ok_files:
        print('publish gate: ' + why); return []
    pre, d, post = split(open(f).read()); keep, held = [], []
    import schema_version
    if layer == 'foodbanks' and not schema_version.accepts(d.get('schema_version')):
        print('publish gate: schema_version %r is not accepted' % d.get('schema_version'))
        return []
    ok = auto_rules.approved(layer, ROOT)
    for i in d['items']:
        pr = [] if i['id'] in live else problems(layer, i)
        if not auto_rules.may_add(layer, RULES) and i['id'] not in live and i['id'] not in ok: pr = ['new place - waiting for your OK (add id to overrides/approved_new_places.json)'] + pr
        (held if pr else keep).append((i, pr))
    if held:
        d['items'] = [i for i, _ in keep]
        open(f, 'w').write(pre + (json.dumps(d) if layer == 'foodbanks' else json.dumps(d, ensure_ascii=False, separators=(',', ':'))) + post)
    lg = load('logs/pending_dean.json', {}); now = datetime.date.today().isoformat()
    lg[layer] = [dict(id=i['id'], name=i.get('name'), postcode=i.get('postcode'), source=i.get('source_url') or i.get('website'), why=pr, held_on=now) for i, pr in held]
    json.dump(lg, open(os.path.join(ROOT, 'logs', 'pending_dean.json'), 'w'), indent=1, ensure_ascii=False)
    md = ['# New places held back for Dean (not published)', '', 'No new place (food bank, shelter or warm space) is added automatically: each waits here for your OK (add its id under its layer in overrides/approved_new_places.json). Approved shelters / warm spaces also need a verified phone number (shelters also a sourced "who it\'s for") before it goes on the map.', '']
    for L, xs in lg.items():
        md += [f'## {L} ({len(xs)})', ''] + [f"- {x['name']} ({x.get('postcode') or ''}) - {', '.join(x['why'])} - {x.get('source') or ''}" for x in xs] + ['']
    pd = os.path.join(ROOT, 'reports', 'pending_dean.md'); keep = ''
    if os.path.exists(pd):  # keep the times review list section written by times_finder.py (Dean, 23 Oct)
        t = open(pd).read()
        for tag in ('times review', 'sweep shelters', 'closures'):  # keep the times review (times_finder) and sweep shelter review sections
            m = re.search(r'(?s)<!-- ' + tag + r' -->.*?<!-- /' + tag + r' -->', t); keep += ('\n\n' + m.group(0) + '\n') if m else ''
    open(pd, 'w').write('\n'.join(md) + keep)
    print(f'publish gate {layer}: {len(held)} new places held for Dean')
    return held
def check():
    gaps = load('overrides/known_gaps.json', {}); bad = []
    for layer in ('shelters', 'warmspaces', 'foodbanks'):
        items = split(open(os.path.join(ROOT, FILES[layer])).read())[1]['items']
        miss = [(i['id'], problems(layer, i)) for i in items if problems(layer, i)]
        if layer == 'foodbanks':
            print(f'food banks without a phone (report only): {len(miss)}'); continue
        known = set(gaps.get(layer, {}))
        bad += [f'{layer}:{k} {p}' for k, p in miss if k not in known]
        print(f'{layer}: {len(miss)} gaps, {len([1 for k, _ in miss if k in known])} listed in overrides/known_gaps.json')
    print('unlisted gaps:', bad or 'none'); return 1 if bad else 0
if __name__ == '__main__':
    sys.exit(check()) if sys.argv[1] == 'check' else gate(sys.argv[1])
