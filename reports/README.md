# reports/

Written by scripts/full_check.py on every 3x-daily refresh.

- daily_review.md / daily_review.json: the day's list for Dean (everything not auto-applied)
- access_tags.json: automatic access flips per pin (clear own-site wording, 2 runs running), re-applied on top of access.js every run
- access_changes.json: log of every automatic access flip and phone fix
- phone_fixes.json: clear new numbers from the bank's own site (single clickable number, seen 2 runs running)
- full_check_state.json: last run's per-site snapshot used to spot changes
