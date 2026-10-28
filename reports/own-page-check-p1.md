# Own-page check, part 1 of 4 (28 Oct 2026)

Read-only report. No data files were changed and nothing was applied. Scope: food bank listings (`type: foodbank`) in `data.full.js` on `main` (commit fda5abbc6), sorted by listing id; part 1 is the first 265 of 1,058: `12-apostles` to `dorking-area` (part 2 starts at `dover`). CSV: `reports/own-page-check-p1.csv`.

## Totals

| | count |
|---|---|
| Listings in part 1 | 265 |
| No own site (Facebook only, or no website) | 27 |
| Own site checked | 238 |
| Own site could not be opened on either read (blocked, captcha, 404) | 22 |
| Matches (phone yes and times yes) | 130 |
| Mismatches (phone or times marked `no`) | 2 |
| Rows marked `apply = yes` | 2 |

- Phone: yes: 190, no: 2, unsure: 31, no number on page: 15, no own site: 27
- Times: yes: 144, no: 0, unsure: 94, no own site: 27

## Mismatches

| id | phone (ours / own page) | times (ours / own page) | apply |
|---|---|---|---|
| `bjo-amara-association` |  / 07450 939946 | unsure | yes |
| `cafe-43-house-of-bread` | 01785243492 / 01785 332413 | unsure | yes |

## How it was checked

- Own site = the listing's `website`. Facebook/Instagram/directories (Trussell central, Give Food, Charity Commission) do not count, so those rows are `no own site`. Trussell-network food bank sites (`<name>.foodbank.org.uk`) are the food bank's own site and were checked.
- Pages read per site: the listing's website, our times source page and evidence page when on the same site, plus up to 6 same-site contact/times/locations pages. JavaScript-built pages were rendered in headless Chromium.
- Every site was read twice, in separate passes. Phone: `yes` when our number's digits appear on an own page (spacing and +44 ignored). `no` only when our number is absent and both reads show exactly one labelled number (not WhatsApp/text, helpline, council or church office); several numbers or doubt gives `unsure`. The own-page phone is copied as printed.
- Times: `yes` when every day/time slot we list is printed on the own site on both reads (day name or day range, then the same start and end, with no other day or 'closed' in between), or our times text appears on the page word for word. `no` only when both reads give identical times from our own times source page, they are not office-like, and none of our slots is printed. Anything else is `unsure` (blocked site, times not readable, reads disagree, our listing has no times, or a different page/centre).
- `apply = yes` only on rows with a certain `no` from two successful reads. Treat these as a review list: nothing was applied by this check.
- Limits: a site can print our times and also other times (another centre or a change notice), and a `yes` does not rule that out; such rows say so in the note column. Sites behind captchas or bot blocks are `unsure`, not mismatches.
