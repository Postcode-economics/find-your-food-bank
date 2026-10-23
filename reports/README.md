# reports/

Written by scripts/full_check.py on every 3x-daily refresh.

- daily_review.md / daily_review.json: the day's list for Dean (everything not auto-applied)
- access_tags.json: automatic access flips per pin (clear own-site wording, 2 runs running), re-applied on top of access.js every run
- access_changes.json: log of every automatic access flip and phone fix
- phone_fixes.json: clear new numbers from the bank's own site (single clickable number, seen 2 runs running)
- full_check_state.json: last run's per-site snapshot used to spot changes

## Standing rule (Dean, 23 Oct 2026 23:36)
Whenever a mistake or a missed source is found, add a regression test for it (tests/test_refresh_upgrade.py) and update
the refresh logic in the same change. Hand-checked times are protected (`"protected": true` in overrides/opening_times.json):
the robots never overwrite them, they only flag differences. Uncertain finder proposals go to the times review list in
reports/pending_dean.md, never onto the map. Facebook pages are re-checked daily (reports/fb_pages_flagged.md), flagged
never removed. Sharp fill-rate drops per source raise an alert at the top of daily_review.md (reports/fill_rates.json).
