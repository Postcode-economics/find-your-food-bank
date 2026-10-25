# Auto-apply rules (Dean, 25 Oct 2026)

Config: `overrides/auto_apply_rules.json` (loaded by `scripts/auto_rules.py`; refresh stops if it is missing). Read by build.py, closure.py, full_check.py, publish_gate.py, refresh_guard.py, build_shelters.py, build_warmspaces.py, sweep_daily.py, swep.py and times_finder.py; tests in `tests/test_auto_apply_rules.py`.

**Needs Dean's OK (never automatic)**
- New places on ANY layer (food banks, shelters, warm spaces, incl. the overnight sweep): held in `reports/pending_dean.md`; added only when the id is under its layer in `overrides/approved_new_places.json` (food banks also `foodbank_approved_new.json` / hand-added `foodbank_added.json`).
- Permanent closures: the pin stays on the map with the card note "May have closed – call before you go" and goes to the pending list (`reports/closures_pending.json`). Removal only by adding the id to `overrides/foodbank_closed.json`.

**Automatic (same result on 2 runs in a row)**
- Opening times and temporary closures; voucher/walk-in flips; a clear single new phone on the food bank's own site; warm space end dates; SWEP open/close; a moved link to the same organisation.
- Dead links are hidden and listed for Dean.
