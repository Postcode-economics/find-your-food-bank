# Self-learning (intelligent mode) - research note

Owner: Dean. Started 25 Oct 2026. This note is kept up to date as each part lands (status column).

## What it is for
The refresh jobs check about 1,060 food bank websites, plus shelter, warm space and council pages, three times a day.
Self-learning decides **which places to check first, how often, and by which method**, so that changes are caught sooner.
It **never decides what is published**.

## Guards (permanent)
- **Never invent data.** Every number comes from files already in the repo. If an input doesn't exist yet (visitor demand, visitor reports, email bounces), it is reported as "no data yet" and has no effect.
- **No place is added or removed without Dean's OK.** See `overrides/auto_apply_rules.json` and `docs/auto_apply_rules.md`:
  - new places wait in `reports/pending_dean.md`;
  - confirmed closures keep their pin with "May have closed – call before you go".
- All existing guards stay: the publish gate, the refresh guard, the 2-run confirmation, the 10% drop stop, schema checks and the "does the result make sense" check.
- The weekly self-review can change a weight by at most 10% a week, and never outside 50–150% of its default.
- Back-off for failing sites never goes past the weekly minimum check (7 days). A strong change signal ends a rest early.
- Opening times from the refresh are written only through the strict gate (`discover.times_gate_apply`, the one hours-apply path): the postcode is on the organisation's own page, the same table is read on 2 separate runs, no other own-site table conflicts, known times never become closed or empty, and Dean has not undone it. Each change is logged once in `reports/times_auto_applied.json` with its source URL and undo (`scripts/times_revert.py`). A missing or unreadable reading leaves the stored week as it is and adds no `pending_dean` row; anything else read is held in `reports/pending_dean.md`. A phone conflict holds the phone fix only; it does not block this hours update.
- Phone numbers are never auto-applied. A clear number is held for Dean (`full_check`, `phone_lock`). Council lines (`council_phone`, `council_ooh`, `council_label`, `council_label_cy`) are never added, changed, copied or removed by a job (#307).

## Safety rails (29 Oct 2026)
`intelligent_mode` in `overrides/auto_apply_rules.json` is **off**. The hours gate (`times_auto_apply`) is unchanged and still on. Turning intelligent mode on adds these rails in `scripts/intelligent_rails.py`. Until then a refresh writes `reports/intelligent_mode.json` for the 8am digest and does not change what is published.

- **Coverage.** If a run opens under 80% of its source pages, skips sites because the full_check budget ran out, gives the hours review no time, or more than a quarter of renders fail (once at least 8 were tried), that step auto-applies nothing. The rest of the data is still published. The run log and the digest get a line starting `INTELLIGENT MODE ALERT`.
- **Stale queue.** A pending times row whose held value already matches the live listing is cleared and not written again.
- **Strict gate.** Two identical reads on separate runs, the organisation's own source, no conflicting hours, known hours never become closed or empty, a logged undo, and no automatic change to a phone or council field.
- **Blast.** More than 40 auto-applies in one run, or in one layer, holds the whole batch.
- **Resilience.** A transient geocoder or page failure is retried, then skipped with a log line. It does not remove a place or blank its times. The 48-hour verification grace is unchanged.
- **Summary.** `reports/intelligent_mode.json` lists applied, held, rejected (with reasons), coverage and errors. `scripts/digest.py` adds an Intelligent mode section only when that file exists.

## Plan in the agreed order, and status
| # | Part | Where | Status |
|---|------|-------|--------|
| core | Reward per useful find, gaps first, back-off for stable or failing sites, weekly minimum check, per-site memory of which method worked | `scripts/learning.py` (used by `full_check.py` and `sweep_daily.py`) | **Live** (25 Oct) |
| 8 | Time-decay: finds and checks fade with a 30-day half-life so a recent result outweighs an old one. Weekly floor unchanged | `learning.reward` / `record` | **Live** (25 Oct) |
| 10 | Learn from Dean's decisions: same-host places move up the queue, and his phone/notice wording is remembered. He is still asked every time. A past yes is not reused | `dean_learning`, signal `dean` | Built 27 Oct (batch 3B) |
| 14 | Cross-source conflicts: when the stored phone is not on the place's own site, flag it for Dean. `chosen` is always null. Nothing is picked | `conflicts`, signal `conflict` | Built 27 Oct (batch 3B) |
| 15 | Weekly accuracy grade (Sundays): a signal whose boosted places found less than the others is turned down one step (at most 10%, and never outside 50–150% of its default). Not enough data: no change. It does not turn a signal up | `accuracy_grades` | Built 27 Oct (batch 3B) |
| 16 | Self-healing fetches: try the method that worked for this site last time, and if it fails try the next. The switch is remembered. A total failure stays a failure | `learning.heal`, `full_check.check_site` | Built 27 Oct (batch 3B) |
| 17 | Change confidence sits under `auto_apply_rules.json`. It can hold back an automatic edit when sources disagree. It cannot allow an add or a removal the rules forbid, and it does not edit the rules file | `learning.allow_under_rules` | Built 27 Oct (batch 3B) |
| 18 | Anomaly brake: if a run would apply many more changes than the last few runs, stop and flag Dean. The count is access flips, phone fixes, hour changes and removals. New places held for Dean do not count. With fewer than four recorded runs it does not stop. Bars: at least 10, at least 3× the median, and at least 8 above that median | `learning.anomaly_brake` / `learning.applied_count` | **Live** (27 Oct) |
| 19 | Monthly drill of that brake, on a copy of the recorded counts. The spike is not stored and `reports/anomaly_brake.md` is not written | `scripts/brake_drill.py` from `learning_signals.build` on the 1st | Built 27 Oct |
| - | Read-only dry-run of the brake on the refresh files already in the repo (`reports/daily_review.json` + `reports/access_changes.json`). Writes nothing | `scripts/brake_dry_run.py` | Check after each refresh |
| 9 | Per-place update rhythm: after two observed gaps between real changes, a place due again by that gap moves up. No guess when the gaps are not there | `learning.rhythm_factor`, signal `rhythm` | **Live** (27 Oct) |
| 11 | Report a problem: submissions recorded in `overrides/problem_reports.json` raise that place's priority. No file means no effect. The listing is not changed | `problem_reports`, signal `problem` | **Live** (27 Oct) |
| 12 | Stale areas: a council whose places were checked longer ago than the typical council moves up. Uses `checked_at` and `district_cache.json` only | `stale_areas`, signal `stale_area` | **Live** (27 Oct) |
| 13 | Demand prediction: cold snaps from `reports/weather.json` (Met Office, via weather.py). Benefit dates and school holidays are used only from a file that names an http source. Otherwise no effect. No dates are invented | `demand_forecast`, signal `forecast` | **Live** (27 Oct) |
| 22 | Source blame: each hand fix (phone, notice, manual closure) is counted against the source that supplied the place. It is a record, not a new value | `source_blame` | **Live** (27 Oct) |
| 20 | Weather: councils named in `reports/weather.json` (scripts/weather.py) move up the next food-bank check and the next council sweep. No file: no effect. Clock times unchanged | `weather_priority`, `sweep_daily._weather_boosts` | **Live** (27 Oct) |
| 3 | Learn from corrections: hand fixes (`overrides/phones.json`, `foodbank_notices.json`, manual `foodbank_closed.json`) lower trust in the source that was wrong and move similar places (same source/host) up | `scripts/learning_signals.py` `corrections()` | Built 25 Oct, merging in this batch |
| 2 | Change signals: dead link (2+ failed runs), closure wording, Facebook page not OK, email bounce (`overrides/email_bounces.json`), stored phone not on the place's own site | `change_signals()` | Built 25 Oct |
| 5 | Source trust with cross-source agreement: the stored phone vs the phones on the place's own site, Beta(1,1) per source, minus the correction rate; less-trusted sources get checked more | `agreement()`, `trust` | Built 25 Oct |
| 1 | Seasonal timing: real changes per ISO week from `logs/entry_history.json` (date-only refreshes ignored); busier weeks get a bounded boost | `seasonal()` | Built 25 Oct (history only starts Oct 2026, so the boost is 0 until it builds up) |
| 4 | Demand weighting from our own visitor numbers | `demand()` reads `reports/demand.json` | Built, **no data yet**: needs a Cloudflare Web Analytics export, so it has no effect until then |
| - | Visitor signals ("Report a mistake") | `visitor()` reads `overrides/visitor_reports.json` | Built, no data yet (reports arrive by email and are added by hand) |
| - | Per-host crawl timing: failure rate per host (and latency where recorded); hard-to-reach hosts are spread out, never dropped | `crawl_timing()` + `full_check.py` per-host pause | Built 25 Oct |
| 7 | Weekly self-review: did the places each signal moved up produce more finds than the rest? Each weight moves ±10% within the bounds | `self_review()`, `weights()` (Sundays) | Built 25 Oct (needs 1 week of data) |
| - | Weekly accuracy trend: share of sites reachable, phone agreement, hand corrections | `trend`, `weekly()` | Built 25 Oct |
| 21 | "What the system learned" in the morning digest, written in plain sentences. Same facts; no new decision | `learning.digest_lines()` + `learning_signals.digest_lines()` in `scripts/digest.py` | **Live** (25 Oct) |
| 6 | Discovery of new places, last | existing discovery (`build.py`, `sweep_daily.py`) feeds the publish gate | Every add is held for Dean's OK (`approved_new_places.json`); a dedicated "found by learning" queue is still to do |

## How it runs
- `full_check.py` orders sites with `learning.plan(..., boosts=learning_signals.boosts())`.
- After the full check, `refresh.yml` runs `scripts/learning_signals.py`. That writes `reports/learning_signals.json`, `reports/learning_review.md` and `reports/learning_state.json`, which the next run uses. The check and refresh clock times are not part of this.
- Tests: `tests/test_learning.py`, `tests/test_learning_signals.py`, `tests/test_learning_dean.py`, `tests/test_learning_conflicts.py`, `tests/test_learning_accuracy.py`, `tests/test_learning_heal.py`, `tests/test_learning_confidence.py`, `tests/test_hours_confirm.py`.
