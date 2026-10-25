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

## Plan in the agreed order, and status
| # | Part | Where | Status |
|---|------|-------|--------|
| core | Reward per useful find, gaps first, back-off for stable or failing sites, weekly minimum check, per-site memory of which method worked | `scripts/learning.py` (used by `full_check.py` and `sweep_daily.py`) | **Live** (25 Oct) |
| 8 | Time-decay: finds and checks fade with a 30-day half-life so a recent result outweighs an old one. Weekly floor unchanged | `learning.reward` / `record` | **Live** (25 Oct) |
| 9 | Per-place update rhythm: after two observed gaps between real changes, a place due again by that gap moves up. No guess when the gaps are not there | `learning.rhythm_factor`, signal `rhythm` | **Live** (25 Oct) |
| 10 | Learn from Dean's decisions: same-host places move up the queue, and his phone/notice wording is remembered. He is still asked every time. A past yes is not reused | `dean_learning`, signal `dean` | **Live** (25 Oct) |
| 11 | Report a problem: submissions recorded in `overrides/problem_reports.json` raise that place's priority. No file means no effect. The listing is not changed | `problem_reports`, signal `problem` | **Live** (25 Oct) |
| 3 | Learn from corrections: hand fixes (`overrides/phones.json`, `foodbank_notices.json`, manual `foodbank_closed.json`) lower trust in the source that was wrong and move similar places (same source/host) up | `scripts/learning_signals.py` `corrections()` | Built 25 Oct, merging in this batch |
| 2 | Change signals: dead link (2+ failed runs), closure wording, Facebook page not OK, email bounce (`overrides/email_bounces.json`), stored phone not on the place's own site | `change_signals()` | Built 25 Oct |
| 5 | Source trust with cross-source agreement: the stored phone vs the phones on the place's own site, Beta(1,1) per source, minus the correction rate; less-trusted sources get checked more | `agreement()`, `trust` | Built 25 Oct |
| 1 | Seasonal timing: real changes per ISO week from `logs/entry_history.json` (date-only refreshes ignored); busier weeks get a bounded boost | `seasonal()` | Built 25 Oct (history only starts Oct 2026, so the boost is 0 until it builds up) |
| 4 | Demand weighting from our own visitor numbers | `demand()` reads `reports/demand.json` | Built, **no data yet**: needs a Cloudflare Web Analytics export, so it has no effect until then |
| - | Visitor signals ("Report a mistake") | `visitor()` reads `overrides/visitor_reports.json` | Built, no data yet (reports arrive by email and are added by hand) |
| - | Per-host crawl timing: failure rate per host (and latency where recorded); hard-to-reach hosts are spread out, never dropped | `crawl_timing()` + `full_check.py` per-host pause | Built 25 Oct |
| 7 | Weekly self-review: did the places each signal moved up produce more finds than the rest? Each weight moves ±10% within the bounds | `self_review()`, `weights()` (Sundays) | Built 25 Oct (needs 1 week of data) |
| - | Weekly accuracy trend: share of sites reachable, phone agreement, hand corrections | `trend`, `weekly()` | Built 25 Oct |
| - | "What the system learned" in the morning digest | `learning.digest_lines()` + `learning_signals.digest_lines()` in `scripts/digest.py` | Core live; signals section in this batch |
| 6 | Discovery of new places, last | existing discovery (`build.py`, `sweep_daily.py`) feeds the publish gate | Every add is held for Dean's OK (`approved_new_places.json`); a dedicated "found by learning" queue is still to do |

## How it runs
- `full_check.py` orders sites with `learning.plan(..., boosts=learning_signals.boosts())`.
- After the full check, `refresh.yml` runs `scripts/learning_signals.py`. That writes `reports/learning_signals.json`, `reports/learning_review.md` and `reports/learning_state.json`, which the next run uses. The check and refresh clock times are not part of this.
- Tests: `tests/test_learning.py` and `tests/test_learning_signals.py`.
