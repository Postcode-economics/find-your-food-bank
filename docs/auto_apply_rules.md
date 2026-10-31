# Auto-apply rules (Dean, 25 Oct 2026)

Config: `overrides/auto_apply_rules.json` (loaded by `scripts/auto_rules.py`; refresh stops if it is missing). Read by build.py, closure.py, full_check.py, publish_gate.py, refresh_guard.py, build_shelters.py, build_warmspaces.py, sweep_daily.py, swep.py and times_finder.py; tests in `tests/test_auto_apply_rules.py`.

**Needs Dean's OK (never automatic)**
- New places on ANY layer (food banks, shelters, warm spaces, incl. the overnight sweep): held in `reports/pending_dean.md`; added only when the id is under its layer in `overrides/approved_new_places.json` (food banks also `foodbank_approved_new.json` / hand-added `foodbank_added.json`).
- Permanent closures: the pin stays on the map with the card note "May have closed – call before you go" and goes to the pending list (`reports/closures_pending.json`). Removal only by adding the id to `overrides/foodbank_closed.json`.

**Automatic (same result on 2 runs in a row)**
- Opening times and temporary closures; voucher/walk-in flips; a clear single new phone on the food bank's own site (strict gate: own host, identical on 2 separate runs, no conflicting own-site number, logged with source URL and undo in reports/phone_auto_applied.json); warm space end dates; SWEP open/close; a moved link to the same organisation.
- Dead links are hidden and listed for Dean.

**Intelligent mode (off)**
`intelligent_mode` is false. While it is false, the rails in `scripts/intelligent_rails.py` do not change what a refresh publishes. When Dean sets it true, a thin read or more than 40 auto-applies in one run or one layer applies nothing from that step, stale queue rows that already match the live listing are cleared, and phones plus every council field stay locked. Each refresh writes `reports/intelligent_mode.json`, which the morning digest reads when the file is there.

## Old links always work (Dean, 25 Oct 2026, permanent rule)
`scripts/old_links.py` opens every helpmap.uk link ever sent out, listed in `scripts/old_links.json`. That covers launch emails, X/Threads/Instagram copy, the signature QR code, area pages, and the forms apps add to links (`?igsh`, `?utm_*`, `?fbclid`, hashes, `/index.html`).

Each link is opened with the Instagram in-app browser at 390px, with an older release's service worker and caches installed first (v85 and v80). The check passes only if the map and the listings come up with no page errors. From v85 onward, the first open must also show the latest build.

Where it runs:
- in CI (`tests.yml` → `old-links`);
- against the live site after every deploy (`deploy-check.yml`), with an automatic revert and an alert if it fails;
- daily at 06:15 UTC.

Add any new link that goes out to `scripts/old_links.json`.

## Click-through user-journey suite (Dean, 25 Oct 2026, permanent rule)
Every site change (any html/css/js, including any future redesign) must pass `scripts/journeys.py`. This is a real-click, headless-browser suite covering all three types at 390px and 1366px, light and dark:
- every search option lands on the chosen list, at the top of the screen with no map in view, nearest first;
- the type tiles;
- Open today on and off, with the exact note wording;
- every filter, including List only, Light mode and ✕;
- the card buttons: Directions, Share, Call, Facebook;
- the pop-up card when a pin is tapped;
- the two-finger note on phones.

Where it runs:
- **Before merge:** the `journeys` job in `.github/workflows/tests.yml`, on every push or PR touching site files. Making it a *required* status check is a GitHub branch-protection setting (Settings → Branches), which only the repo owner can switch on.
- **After each deploy:** `.github/workflows/deploy-check.yml` runs the suite (after the old-links check) against https://helpmap.uk. If it fails, the deploying commit is reverted automatically and a `journeys` alert issue is opened.
- **Daily:** the same workflow at 06:15 UTC (alert only).

Nothing goes live unless every check passes.

## Card design lock (Dean 25 Oct 2026, permanent)
`scripts/design_lock.py` (colours in `scripts/design_lock.json`) checks list cards and pin pop-up cards on all three types at
390 and 1366 px, light and dark: green call button shows the number and its tel: link matches; yellow Directions to Google Maps;
Share / text this address; Message on Facebook only where there is no phone (verified facebook.com URL); website / Give Food /
source links; Report a problem; food bank type badge; status dot colours locked (red closed, green open, grey unknown);
tap targets at least 44 px; a cheap live map-tile load check; call/Facebook button counts must not drop over 3% below the v87 baseline.
Runs in CI (`tests.yml` design-lock job), after every deploy and daily (`deploy-check.yml`, auto-revert on failure).
'Times unknown while times are listed' fails the design lock (`ENFORCE_TIMES`). A partial week shows the next listed opening; text-only times say to check the lines below.

## Status line and list alignment
Status line: fixed font, one line, fixed header height, never an ellipsis; 'X near Place' falls back to 'Place'; ', County' is
dropped and the two over-long council names use 'Craigavon' / 'Bournemouth' (`V3SHORT` in v3.js, confirmed by Dean 25 Oct).
`tests/test_status_line.py` and `tests/test_list_alignment.py` (same left edge for every note, heading and card) run in the
`browser-tests` CI job.

## Emergency shelters (natural disasters), approved by Dean 25 Oct 2026
1. Reuse the existing official feeds in `scripts/weather.py` (point 27: EA flood warnings, SEPA, NRW, Met Office). Do not rebuild them; extend them (link warnings to rest centres, banner, expiry).
2. A red area banner ('Flood warning in your area – see emergency shelters') shows when a warning covers the searched area.
3. Every emergency listing has an 'open until' time and disappears automatically when it passes.
4. Emergency cards show 'Life in danger? Call 999' and Floodline 0345 988 1188.
5. A low-data text-only emergency list is provided.
6. Access, pets and beds icons are shown only if the source states them, never guessed.
7. Official council rest centres may go live automatically in a fast-moving disaster and are flagged to Dean afterwards. Everything else needs Dean's OK first.
8. A monthly drill runs on a test copy only (never live), and a preview goes to Dean before any build.

Warning monitoring (approved by Dean 25 Oct 2026; build only after Dean has seen the preview):
- A GitHub workflow runs the `weather.py` warning check every 10 minutes. It is read-only and publishes only on a real warning.
- hello@helpmap.uk is signed up to the EA, SEPA and NRW flood warning emails as a second route.
- A watchdog alerts if the check hasn't run for 1 hour.
- Dean is messaged immediately on any severe or evacuation alert.

## Header wording rule (Dean 25 Oct 2026)
'Food banks near you' / 'Shelters near you' / 'Warm spaces near you', or '… near Place'. One line only, fixed font size, the box
never grows, never an ellipsis. If it doesn't fit, show just the place name. ', County' is dropped from the place name.

## Screenshots to Dean
Screenshots sent to Dean must never show error tiles from a local or demo copy: use the live site, or a working tile source.

## Phone contacts (Dean 26 Oct 2026, 08:29, rule 21)
A verified number that the venue's own source page gives as its contact is shown, including a named person's or personal number, with the label that page gives (for example Team Rector, Pastor). A host church's contact page counts as that venue's own page (Dean 26 Oct 2026, 08:37). `scripts/phone_rule.py` runs from `build.py`, `shelter_contacts.py` and `full_check.py`. A reason that only says the number is personal does not hold it back. An unverified or doubtful number stays off, with the reason in `overrides/phone_holds.json`. Dean's own phone numbers and personal emails in `overrides/never_publish.json` are never copied onto a place. The public address hello@helpmap.uk is not in that file.

## Theme default (Dean 25 Oct 2026)
STANDING RULE (Dean, 25 Oct 2026, asked 3 times): helpmap.uk opens in DARK mode by default, ignoring the OS/phone light preference. Only the visitor's own saved Light mode choice overrides it; if storage fails (Instagram in-app browser) the site is dark. Guarded by tests/test_default_dark.py, tests/test_dark_default_engines.py, tests/test_webkit_instagram.py (WebKit, OS light) and scripts/dark_default.py in the live Deploy check. First-time visitors with no saved theme get DARK, whatever their phone setting. A saved choice (localStorage 'light') is always
kept, and is applied by an inline script in <head> before first paint (no flash). Test: tests/test_default_dark.py.

## Latest main only (Dean 26 Oct 2026, permanent rule)
Every change is applied to the latest `main` only. Bring the branch up to date by merging `main` in (never force-push), then open a pull request. Do not merge it until the checks have passed.

## Dark mode details (Dean 26 Oct 2026, 06:46)
- Map tiles stay the normal light tiles in dark mode. Do not darken, invert or recolour the map.
- Call 999 stays bold white text and a white icon on emergency red `#FF3B30` in light and in dark.
- In dark mode the postcode box is a dark field: card background, light text, a readable placeholder, and the gold focus outline. Its size, font and layout stay the same as light mode. Test: `tests/test_dark_search.py`.
