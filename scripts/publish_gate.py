"""Publish gate (Dean, 23 Oct 2026). Runs in every shelters / warm spaces / food bank refresh, before the refresh guard.

PRIVATE_BLOCKLIST (rule 9) is a GitHub Actions secret, never a file in this repo. Set it under
Settings → Secrets and variables → Actions, name PRIVATE_BLOCKLIST, one address or phone per line.
The refresh workflows pass secrets.PRIVATE_BLOCKLIST into this step. When the secret is set and a
listing matches, that listing is held back without copying the secret, and this step exits non-zero.
Logs print the match count only. See scripts/private_block.py.
gate <layer>: a NEW place (not in the live file, git HEAD) is not published unless it has a verified phone
  (own number 'tel'; for shelters / warm spaces a labelled council homeless/out-of-hours line also counts) and,
  for shelters, a sourced 'who it's for' (groups). Held places go to logs/pending_dean.json + reports/pending_dean.md.
  Existing places are never removed here (the refresh guard keeps their fields), except a private-blocklist
  match, which is held back whether or not it is already on the map.
check: CI. Fails if a published shelter lacks a phone or groups, or a warm space lacks a phone, unless the id is
  listed in overrides/known_gaps.json (existing gaps being worked on, each with a note). Food banks without a
  phone are reported only (count printed), never failing, so the live map is not blocked. A private-blocklist
  match fails this check for every layer, including food banks."""
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
    if layer == 'shelters' and not i.get('groups') and i.get('who_for') != 'Not stated':  # Dean 1 Nov 2026 option A: a hand-set 'Not stated' is a sourced answer
        p.append("no sourced 'who it's for'")
    return p
def load(p, d):
    try: return json.load(open(os.path.join(ROOT, p)))
    except Exception: return d
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules, private_block; RULES = auto_rules.load()  # Dean 25 Oct 2026
def approved_new():
    """Dean 25 Oct 08:20: no new food bank is auto-added. Only ids Dean OK'd (overrides/foodbank_approved_new.json) or
    hand-added (overrides/foodbank_added.json) may go on the map; everything else waits in reports/pending_dean.md."""
    ok = set()
    for f in ('overrides/foodbank_approved_new.json', 'overrides/foodbank_added.json'):
        ok |= {k for k in load(f, {}) if not k.startswith('_')}
    return ok

def _arcgis_feed_urls(root=ROOT):
    cfg = load('overrides/arcgis_warmspaces.json', {})
    return {f.get('url') or '' for f in (cfg.get('feeds') or []) if f.get('url')}

LANCS_HOLD = "Lancashire feed not yet confirmed for 2026-27"
STILL_WATERS_HOLD = "Cherwell Still Waters: phone only on council feed, not on venue website"


def warmspace_publish_holds(i):
    pr = []
    iid = str(i.get("id") or "")
    if iid.startswith("lancs-"):
        pr.append(LANCS_HOLD)
    if iid.startswith("cherwell-") and "still-waters" in iid:
        pr.append(STILL_WATERS_HOLD)
    return pr


def council_listed_warmspace(i, root=ROOT):
    """Dean 31 Oct 2026 18:31 GMT: a council ArcGIS warm-space row with address and verified phone publishes without per-id OK."""
    if warmspace_publish_holds(i):
        return False
    if not (i.get('address') or i.get('postcode')):
        return False
    if problems('warmspaces', i):
        return False
    src = i.get('source_url') or i.get('evidence_url') or ''
    return src in _arcgis_feed_urls(root)
def _row(i, pr, now, secrets):
    """Pending row. A private-blocklist hit copies no name, address, phone, or source."""
    if secrets and private_block.matches(i, secrets):
        return dict(id=private_block.safe_id(i, secrets), name='', postcode='', source='', why=['private details — not published'], held_on=now)
    return dict(id=i['id'], name=i.get('name'), postcode=i.get('postcode'), source=i.get('source_url') or i.get('website'), why=pr, held_on=now)
def gate(layer, ref='HEAD'):
    """A held hand file or a rejected schema_version blocks the publish (gate.blocked, non-zero exit), but the
    new-place, phone and private-blocklist checks still run, so nothing they hold can reach the map."""
    gate.last_privacy = False; gate.blocked = ''
    f = os.path.join(ROOT, FILES[layer])
    secrets = private_block.entries()
    live_council = None
    try:
        live_items = split(subprocess.check_output(['git', 'show', f'{ref}:{FILES[layer]}'], cwd=ROOT, text=True))[1]['items']
        live = {i['id'] for i in live_items}
        import phone_lock
        live_council = phone_lock.live_council(live_items)
    except Exception:
        if not secrets:
            print('gate: no live baseline, skipped'); return []
        live = None  # no baseline: still hold a private-blocklist match (rule 9)
    import override_check
    ok_files, why = override_check.assess(ROOT)
    if not ok_files:
        gate.blocked = why; print('publish gate: ' + why + ' - publish blocked')
    pre, d, post = split(open(f).read()); keep, held = [], []
    import schema_version
    if layer == 'foodbanks' and not schema_version.accepts(d.get('schema_version')):
        gate.blocked = 'schema_version %r is not accepted' % d.get('schema_version')
        print('publish gate: ' + gate.blocked + ' - publish blocked')
    ok = auto_rules.approved(layer, ROOT)
    import phone_lock
    dirty = False
    for i in d['items']:
        if phone_lock.settle_council(i): dirty = True  # no verified out-of-hours line: council line stays hidden
    for i in d['items']:
        pr = warmspace_publish_holds(i) if layer == 'warmspaces' else []
        if live is None:
            if not pr:
                pr = []
        else:
            if i['id'] not in live:
                pr = pr + problems(layer, i)
            if layer == 'foodbanks' and i['id'] in ok:
                pr = [p for p in pr if p != 'no verified phone']  # Dean-approved food banks may have no published phone (verified details only, 26 Oct)
            auto_hostel = (layer == 'shelters' and i.get('card_type') == 'referral_hostel'
                           and (RULES.get('referral_hostel_auto_add') or {}).get('on')
                           and i.get('phone') and (i.get('town') or i.get('area'))
                           and not i.get('postcode') and not isinstance(i.get('lat'), (int, float))
                           and not isinstance(i.get('lng'), (int, float)))
            if not auto_hostel and not auto_rules.may_add(layer, RULES) and i['id'] not in live and i['id'] not in ok:
                if not (layer == 'warmspaces' and council_listed_warmspace(i)):
                    pr = ['new place - waiting for your OK (add id to overrides/approved_new_places.json)'] + pr
        if secrets and private_block.matches(i, secrets):
            pr = ['private details — not published']
            gate.last_privacy = True
        if layer == 'shelters':
            import google_handcheck
            why = google_handcheck.held_reason(i, root=ROOT)
            if why: pr = [why] + [p for p in pr if p != why]  # already-live man-google rows are held too
        (held if pr else keep).append((i, pr))
    if phone_lock.guard([i for i, _ in keep], ROOT, via='publish', source='publish gate', layer=layer, persist_new=True, published=live_council):
        dirty = True
    if held or dirty:
        d['items'] = [i for i, _ in keep]
        open(f, 'w').write(pre + (json.dumps(d) if layer == 'foodbanks' else json.dumps(d, ensure_ascii=False, separators=(',', ':'))) + post)
    lg = load('logs/pending_dean.json', {}); now = datetime.date.today().isoformat()
    lg[layer] = [_row(i, pr, now, secrets) for i, pr in held]
    if layer == 'warmspaces':
        lg[layer] = [x for x in lg[layer] if LANCS_HOLD not in x.get('why', [])]
        for s in load('logs/arcgis_lancs_pending.json', []):
            lg[layer].append(dict(id='lancs-pending-%s' % (s.get('objectid') or 'x'), name=s.get('name'), postcode=s.get('postcode'),
                                  source='Lancashire County Council warm spaces', why=[LANCS_HOLD], held_on=now))
    json.dump(lg, open(os.path.join(ROOT, 'logs', 'pending_dean.json'), 'w'), indent=1, ensure_ascii=False)
    md = ['# New places held back for Dean (not published)', '', 'No new place (food bank, shelter or warm space) is added automatically: each waits here for your OK (add its id under its layer in overrides/approved_new_places.json). Approved shelters / warm spaces also need a verified phone number (shelters also a sourced "who it\'s for") before it goes on the map.', '']
    for L, xs in lg.items():
        md += [f'## {L} ({len(xs)})', ''] + [f"- {x['name']} ({x.get('postcode') or ''}) - {', '.join(x['why'])} - {x.get('source') or ''}" for x in xs] + ['']
    pd = os.path.join(ROOT, 'reports', 'pending_dean.md'); keep = ''
    if os.path.exists(pd):  # keep the times review list section written by times_finder.py (Dean, 23 Oct)
        t = open(pd).read()
        for tag in ('times review', 'times crosscheck fb', 'times crosscheck sh', 'times crosscheck ws', 'sweep shelters', 'closures', 'phone lock', 'council line undo', 'rest centre switch-on', 'emergency switch-on', 'held near cities', 'day centre candidates', 'referral hostel holds'):  # keep tagged sections in pending_dean.md
            m = re.search(r'(?s)<!-- ' + tag + r' -->.*?<!-- /' + tag + r' -->', t); keep += ('\n\n' + m.group(0) + '\n') if m else ''
    open(pd, 'w').write('\n'.join(md) + keep)
    try:
        import city_watch
        city_watch.write_held_section(ROOT)
    except Exception as ex:
        print('held near cities skipped: %s' % ex)
    if gate.last_privacy:
        n = private_block.match_count([i for i, _ in held], secrets)
        print(f'publish gate {layer}: PRIVATE_BLOCKLIST matched {n} listing(s) — not published')
    print(f'publish gate {layer}: {len(held)} new places held for Dean')
    return held
def check():
    gaps = load('overrides/known_gaps.json', {}); bad = []
    secrets = private_block.entries()
    for layer in ('shelters', 'warmspaces', 'foodbanks'):
        items = split(open(os.path.join(ROOT, FILES[layer])).read())[1]['items']
        miss = [(i['id'], problems(layer, i)) for i in items if problems(layer, i)]
        if layer == 'foodbanks':
            print(f'food banks without a phone (report only): {len(miss)}')
        else:
            known = set(gaps.get(layer, {}))
            bad += [f'{layer}:{k} {p}' for k, p in miss if k not in known]
            print(f'{layer}: {len(miss)} gaps, {len([1 for k, _ in miss if k in known])} listed in overrides/known_gaps.json')
        if layer == 'shelters':
            import google_handcheck
            bad += ['%s: %s' % (i['id'], google_handcheck.REASON) for i in items if google_handcheck.held_reason(i, root=ROOT)]
        if secrets:
            n = private_block.match_count(items, secrets)
            if n:
                bad += [f'{layer}: {n} private blocklist']
    print('unlisted gaps:', bad or 'none'); return 1 if bad else 0
if __name__ == '__main__':
    if sys.argv[1] == 'check': sys.exit(check())
    gate(sys.argv[1])
    if gate.blocked: sys.exit(1)
    sys.exit(1 if gate.last_privacy else 0)
