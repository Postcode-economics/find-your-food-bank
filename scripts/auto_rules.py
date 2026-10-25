"""Dean 25 Oct 2026 auto-apply rules (overrides/auto_apply_rules.json). Missing/invalid file = hard failure, never a silent default."""
import json, os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'overrides', 'auto_apply_rules.json')
def load():
    r = json.load(open(P, encoding='utf-8'))  # raises if missing: refresh must stop
    for k in ('add_new_places', 'remove_confirmed_closures', 'closure_card_note', 'confirm_runs'): assert k in r, 'auto_apply_rules.json missing ' + k
    return r
