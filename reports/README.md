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

## Lesson (24 Oct 2026): the sweep never adds shelters to the map
The daily sweep could add shelters found on council pages (including the SWEP pages swep.py discovers) straight onto the map, marked "Unverified - call before you go". That breaks Dean's standing rule: unsure finder results go to his review list, never straight onto the map. None had been added, but it could have happened. Now `scripts/sweep_daily.py` sends every shelter candidate to the "Shelter candidates from the sweep" section of `reports/pending_dean.md` only (tests: `tests/test_sweep.py` NoShelterAdds). The same rule already applies to opening times (times_finder, review only). Any new finder must be review-only by default.

## Lesson (24 Oct 2026): conditional SWEP wording is not an activation
Durham's page said "This web page will be updated if SWEP is activated" and was marked active. swep.classify now ignores any
activation phrase whose sentence contains conditional wording (if, when, whenever, during, once, until, as soon as, in the event,
in periods of, under these conditions, will be updated). The 3x-daily watcher, the daily full check and the alert-triggered
re-check (weather.py) all use this rule. 16 councils were cleared the same way. Only a plain present-tense statement
("SWEP is currently active") counts; tests in tests/test_swep.py (ConditionalWording).
