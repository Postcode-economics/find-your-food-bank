# reports/

Written by scripts/full_check.py on every 3x-daily refresh.

- daily_review.md / daily_review.json: the day's list for Dean (everything not auto-applied)
- access_tags.json: automatic access flips per pin (clear own-site wording, 2 runs running), re-applied on top of access.js every run
- access_changes.json: log of every automatic access flip and phone fix
- phone_fixes.json: clear new numbers from the bank's own site (single clickable number, seen 2 runs running)
- full_check_state.json: last run's per-site snapshot used to spot changes

## Rule (30 Oct 2026, Dean): verified items go on without asking
Recorded in `overrides/auto_apply_rules.json` as `times_finder_rule` and `verified_pending_rule` so every session and refresh carries them.

**Times finder (08:46 GMT):** opening times the times finder finds always go on automatically, with no approval gate. The strict two-run check (identical reads on 2 separate runs from the organisation's own source, plus all other strict gates) is the only safety net; anything that fails it is held, not sent to Dean for approval.

**Verified pending (08:51 GMT):** once an item on the pending list (new places, phone and council-line changes, opening times, shelters) has been hand-checked and verified against its own reliable source by Grok Bot, it goes on without asking Dean again, through a normal reviewed PR with full tests and a live check. Unverified or doubtful items stay held. Refreshes still never change phones or council lines on their own: the phone lock stays; verified changes go in via those PRs.

## Standing rule (Dean, 23 Oct 2026 23:36)
Whenever a mistake or a missed source is found, add a regression test for it (tests/test_refresh_upgrade.py) and update
the refresh logic in the same change. Hand-checked times are protected (`"protected": true` in overrides/opening_times.json):
the robots never overwrite them, they only flag differences. Uncertain finder proposals go to the times review list in
reports/pending_dean.md, never onto the map. Facebook pages are re-checked daily (reports/fb_pages_flagged.md), flagged
never removed. Sharp fill-rate drops per source raise an alert at the top of daily_review.md (reports/fill_rates.json).

## Lesson (29 Oct 2026, Dean): a refresh never adds, changes, copies or removes a council line
The 29 Oct 05:44 warm spaces refresh gave 16 warm spaces a `council_phone` copied from their `council_ooh`, so a council line button
appeared on their cards. The copy came from `phone_lock.settle_council` and from the same value in `overrides/warmspaces_contacts.json`.
`phone_lock.guard` let it through because it compared only with `overrides/phone_baseline.json`, and the baseline already held that
copy: `phone_baseline.py generate` ran `settle_council` before freezing (27 Oct 21:32). The 27 Oct 22:20 merge then published the file
without it. Now `guard(published=...)` locks every council-line field (`council_phone`, `council_ooh`, `council_label`, `council_label_cy`)
to the live bytes for warm spaces, shelters and food banks. A new place gets no council line until Dean OKs one, and any proposal,
including a baseline that differs from the live file, is held under "phone lock" in `pending_dean.md`. The baseline freezes the published
council bytes, never derived ones. Undo log: `council_line_changes.json`. Tests: `tests/test_council_line_lock_29oct.py`.

## Lesson (24 Oct 2026): the sweep never adds shelters to the map
The daily sweep could add shelters found on council pages (including the SWEP pages swep.py discovers) straight onto the map, marked "Unverified - call before you go". That breaks Dean's standing rule: unsure finder results go to his review list, never straight onto the map. None had been added, but it could have happened. Now `scripts/sweep_daily.py` sends every shelter candidate to the "Shelter candidates from the sweep" section of `reports/pending_dean.md` only (tests: `tests/test_sweep.py` NoShelterAdds). The same rule already applies to opening times (times_finder, review only). Any new finder must be review-only by default.

## Lesson (24 Oct 2026): conditional SWEP wording is not an activation
Durham's page said "This web page will be updated if SWEP is activated" and was marked active. swep.classify now ignores any
activation phrase whose sentence contains conditional wording (if, when, whenever, during, once, until, as soon as, in the event,
in periods of, under these conditions, will be updated). The 3x-daily watcher, the daily full check and the alert-triggered
re-check (weather.py) all use this rule. 16 councils were cleared the same way. Only a plain present-tense statement
("SWEP is currently active") counts; tests in tests/test_swep.py (ConditionalWording).

## Lesson (24 Oct 2026 11:45, Dean): general descriptions are not "active"
Bolton ("has been put in place to support…") and Rotherham ("is in place to support people…") were marked active from
descriptions of what SWEP is. swep.classify now counts an activation only when the page clearly says SWEP is on now: the
wording itself says currently / now / tonight / today / this evening / with immediate effect / from <date or day>, or it is a
specific notice ("has been activated / triggered", which the old-notice date check still screens). Any "… in place to support /
help / protect / ensure / prevent" counts as a description. The watcher, daily full check and alert re-check (weather.py) all
use this rule. Tests: tests/test_swep.py ClearlyOnNow, tests/test_weather.py test_recheck_general_description_goes_to_review.
