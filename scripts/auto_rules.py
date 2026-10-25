"""Dean 25 Oct 2026 auto-apply rules (overrides/auto_apply_rules.json). Missing/invalid file = hard failure, never a silent default."""
import json, os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'overrides', 'auto_apply_rules.json')
def load():
    r = json.load(open(P, encoding='utf-8'))  # raises if missing: refresh must stop
    for k in ('add_new_places', 'remove_confirmed_closures', 'closure_card_note', 'confirm_runs'): assert k in r, 'auto_apply_rules.json missing ' + k
    return r

APPROVED = os.path.join(os.path.dirname(P), 'approved_new_places.json')
def approved(layer, root=None):
    """Ids Dean OK'd as new places for this layer."""
    base = os.path.join(root, 'overrides') if root else os.path.dirname(P); ok = set()
    try: ok |= {k for k in json.load(open(os.path.join(base, 'approved_new_places.json'), encoding='utf-8')).get(layer, {})}
    except Exception: pass
    if layer == 'foodbanks':
        for f in ('foodbank_approved_new.json', 'foodbank_added.json'):
            try: ok |= {k for k in json.load(open(os.path.join(base, f), encoding='utf-8')) if not k.startswith('_')}
            except Exception: pass
    return ok
def may_add(layer, rules=None): return bool((rules or load())['add_new_places'].get(layer))
