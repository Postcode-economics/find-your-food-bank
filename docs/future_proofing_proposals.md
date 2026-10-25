# Future-proofing proposals

Owner: Dean. Written 25 October 2026, after the 14 sweep upgrades.

**Proposals only.** Nothing in this note is switched on, and nothing here should be built from this file alone. Each item needs its own yes before any code.

## Hard rules that still apply

- Never invent data. A missing file, a missing date, or a missing district means no effect.
- Never add or remove a place unless Dean says so. `overrides/auto_apply_rules.json` stays as it is: `add_new_places` false, `remove_confirmed_closures` false, `confirm_runs` 2. The automatic list stays the list already written there.
- Check and refresh clock times do not move. A signal may only reorder places inside a run that was already going to happen.
- Every place is still checked at least weekly (`FLOOR_DAYS` 7). All signals share the one boost cap (`BOOST_CAP` 3.0).
- When sources disagree, flag it. Never pick a value.

Effort: **S** is one small change with a test, **M** is a few files and tests, **L** is a new store or a long replay harness.

## Already in place (do not rebuild)

Atomic saves of the learning state (write a temp file, then replace). The combined boost cap and the weekly floor. The anomaly brake. Playwright pinned in `requirements.txt` (`playwright==1.47.0`); the scripts otherwise use the Python standard library. School holidays left unused on purpose, because there is no single official UK source. Confirmed closures stay on the map with a "call before you go" note. Self-heal only switches a fetch between plain HTTP and HTTPS for a site that already worked one of those ways. It does not repair a parser when the page HTML changes.

## Recommend yes

### 1. Notice when a page answers but the parser finds nothing

- **Benefit:** A site that still returns HTTP 200, but whose parser suddenly extracts no records, is flagged before weeks of silent empty checks.
- **Risk:** A genuinely empty week (a council page between seasons) looks like a broken parser and moves that site up the queue.
- **Effort:** M.
- **Conflict:** None with the 14 or the hard rules, as long as the only result is a flag and a higher place in the existing queue. It complements self-heal, which cannot see a change of HTML. The IFAN parser already refuses a result of under 200 records; this would make that kind of check general and visible in the morning note.
- **Recommendation:** Yes.

### 2. Watch for a whole source disappearing

- **Benefit:** If Give Food, IFAN, or a council directory stops answering, Dean hears "this source is gone" instead of a slow drip of single dead links.
- **Risk:** A short outage is mistaken for a permanent loss and the morning note nags.
- **Effort:** S.
- **Conflict:** None if the place stays on the map. Overlaps the existing dead-link signal and the sweep abort when more than half the pages fail. Those stay. This is a separate flag for the source, not a removal.
- **Recommendation:** Yes, flag only.

### 3. A dependency pin report, never an automatic upgrade

- **Benefit:** The morning note says whether the runner still matches the pinned Playwright, and names anything imported that is not pinned, before a silent upgrade changes a scrape.
- **Risk:** The note is noisy if the runner image drifts for a harmless reason.
- **Effort:** S.
- **Conflict:** None. An automatic upgrade is a separate idea and is recommended no (below).
- **Recommendation:** Yes.

### 4. A version number on the published data

- **Benefit:** `data.js` carries a `schema_version`, and the site accepts the current version and the one before, so a field rename does not blank the map for everyone on an old cached page.
- **Risk:** A version bump that skips a number, or a reader that only accepts the newest file, takes the map down. Bump only when a field really changes, and keep N and N-1 both valid.
- **Effort:** M.
- **Conflict:** None with the 14. They do not publish map data. Today's `schema_errors()` in `scripts/recheck.py` checks fields and UK coordinate ranges, but there is no version stamp.
- **Recommendation:** Yes.

### 5. Spot a new official feed, and only flag it

- **Benefit:** When a council or a directory page we already fetch links a new official list, that URL is shown to Dean.
- **Risk:** A news article or a blog is mistaken for an official list.
- **Effort:** M.
- **Conflict:** Auto-adding the places inside that feed would break the hard rule. This proposal does not. The list of "official" starting URLs is hand-maintained. A new URL is a line in the morning note, never a new pin.
- **Recommendation:** Yes, flag only.

### 6. A cost and rate-limit ledger

- **Benefit:** Each run records how many calls it made to postcodes.io, Natural Resources Wales, the Met Office feeds, and Facebook, and pauses a host that answers 429 for the rest of that run.
- **Risk:** A pause that drops the weekly check. The remainder has to be picked up by a later run that was already scheduled, not by a new clock time, and not by skipping the place.
- **Effort:** M.
- **Conflict:** None if the cron lines stay byte-for-byte and the weekly floor stays. The NRW flood call already depends on `NRW_FLOOD_API_KEY`; this counts it, it does not invent warnings when the key is missing.
- **Recommendation:** Yes.

### 7. Prune learning scores that have not been seen for about 90 days

- **Benefit:** `reports/learning_state.json` does not grow forever with sites that have left the lists, so a sweep stays fast years from now.
- **Risk:** A pruned place is treated as new for ordering, so it jumps toward the front of the next queue. That is exploration, not a new pin. Rhythm and faded scores for that place are forgotten.
- **Effort:** S.
- **Conflict:** Mild with time-decay and per-place rhythm, because those memories live on the key that would be pruned. It does not conflict with the hard rules. Keep a tombstone (the key, the last day, and "pruned") so the forgetfulness is visible. The weekly floor applies again as soon as the place is seen.
- **Recommendation:** Yes, with the tombstone.

### 8. One saved example page per parser

- **Benefit:** A test fails when a parser edit would no longer read a page shape we already accepted, which is the usual way a scraper rots.
- **Risk:** The saved page goes stale and blocks a real fix. Replace the example only when Dean accepts the new shape.
- **Effort:** M.
- **Conflict:** None. Store the smallest HTML that the parser needs, not a full personal page.
- **Recommendation:** Yes.

### 9. Replay from the fields we already extracted, not from saved HTML

- **Benefit:** A future bug can be re-run against the hours hash, the phone list, and the HTTP status we stored, without keeping page text for years.
- **Risk:** Saving full HTML would keep names, phones and addresses we do not need. This proposal refuses that.
- **Effort:** L.
- **Conflict:** None. Do it after the example pages in item 8, which are the smaller step.
- **Recommendation:** Yes, later.

### 10. Label dates in UK time, and leave the clock times alone

- **Benefit:** The morning note says which London day and time a run was, so a 4am UTC job in summer is not misread as 4am British Summer Time.
- **Risk:** Someone "corrects" the GitHub cron into London time and shifts every run. The tests that lock the cron strings have to stay.
- **Effort:** S.
- **Conflict:** None if the cron lines are not edited. The workflows stay on `29 4,12,20`, `41 4,12,20`, `53 4,12,20`, `5 3,11,19`, `0 5`, `40 6`, `17 * * * *`, and `15 6`.
- **Recommendation:** Yes.

### 11. Check the override files before a publish

- **Benefit:** A broken or suddenly much smaller `phones.json`, notices file, or closures file stops the publish and tells Dean, instead of wiping hand corrections.
- **Risk:** A real bulk edit Dean just made is held until he confirms it. That is the point of the check.
- **Effort:** S.
- **Conflict:** None. The anomaly brake watches how many places a run would change. This watches the hand files themselves.
- **Recommendation:** Yes.

### 12. A weekly change count that outlives the 50-change cap

- **Benefit:** Season comparison can still work in later years. `logs/entry_history.json` keeps only the last 50 changes per place, so a busy place forgets earlier years, and the file also stores old and new phones and addresses.
- **Risk:** Counting ordinary "website/feed update" noise as a busy week. Count only the same real changes the season signal already uses.
- **Effort:** S.
- **Conflict:** None with time-decay. Decay fades the learning score. This is a separate tally of how many real changes fell in each ISO week, with no names and no phone numbers. Until two years of tallies exist, the season boost stays as it is today (no boost while the history is short). Do not invent a seasonal pattern before then.
- **Recommendation:** Yes.

### 13. Remember old phones and addresses for 90 days, then drop the text

- **Benefit:** The change log stops holding old phone numbers and addresses forever, while the label ("phone changed on this date") remains.
- **Risk:** After 90 days the morning note cannot show the previous phone. Git history of the data file still can.
- **Effort:** S.
- **Conflict:** None with source-blame, which reads the hand-correction files, not this log.
- **Recommendation:** Yes.

### 14. Treat a robots.txt disallow as a result, not as a hint to guess

- **Benefit:** When a site's robots.txt disallows the page, that fact is recorded, the own-site fetch is skipped, and opening hours are not guessed from a page we were asked not to read.
- **Risk:** A very broad disallow stops a useful check. Dean is told, and another method that is allowed can still run. The place is not deleted.
- **Effort:** M.
- **Conflict:** The weekly floor is not permission to ignore robots. The check still happens by an allowed method, or it is reported as blocked. `sweep_daily.py` already reads robots.txt to find sitemaps. `discover.py` already refuses to let robots overwrite hand-checked times. This proposal extends that caution to the fetch itself.
- **Recommendation:** Yes.

### 15. Write down why an automatic edit was allowed

- **Benefit:** Each automatic change (opening times, a temporary closure, a voucher or walk-in flip, one clear new phone, a warm-space end date, SWEP open or close, a moved link to the same organisation) keeps the rule name, the confidence, and the source URL beside it.
- **Risk:** The note gets treated as a new source of truth. It is a log. The rules file still decides.
- **Effort:** S.
- **Conflict:** None. Change confidence already sits under `auto_apply_rules.json` and can only hold a change back. This records the decision. It does not widen the automatic list.
- **Recommendation:** Yes.

### 16. A monthly drill of the anomaly brake, on a copy

- **Benefit:** Once a month we prove the brake would still stop a run that tried to change far more places than usual, without waiting for a real accident.
- **Risk:** The drill writes the real `reports/anomaly_brake.md` or the real learning state. It must use a temporary copy and publish nothing.
- **Effort:** M.
- **Conflict:** None with the live brake. The drill does not add the fake spike to the real baseline.
- **Recommendation:** Yes.

### 17. Report postcode-to-council cache gaps, and do not fill them by guessing

- **Benefit:** The morning note says how many food-bank postcodes have no row in `overrides/district_cache.json`, which is the only council lookup used for stale areas and weather.
- **Risk:** Someone fills a gap by guessing the council from the postcode prefix. That is invented geography and would move the wrong councils up.
- **Effort:** S.
- **Conflict:** None if a missing row means no area boost, which is already the rule. Do not call postcodes.io from this report, and do not invent a district.
- **Recommendation:** Yes, report only.

### 18. Say when the weather key failed, without inventing a warning

- **Benefit:** If `reports/weather.json` records a 401 or 403, or the Natural Resources Wales key is missing, the morning note says the feed failed. Councils are not moved up.
- **Risk:** A key failure is mistaken for a weather warning. The note must not add areas.
- **Effort:** S.
- **Conflict:** None with the weather upgrade, which already does nothing when a warning has no area.
- **Recommendation:** Yes.

### 19. A draft inbox for "Report a problem" emails

- **Benefit:** Problem emails waiting in Dean's inbox can sit in a draft file, so the priority signal is not stuck until someone retypes them by hand.
- **Risk:** A bad parse files the wrong place, or copies a visitor's free text onto the map.
- **Effort:** M.
- **Conflict:** It would conflict with the problem-report upgrade, and with "never invent", if the draft applied itself. It must do nothing until Dean copies a row into `overrides/problem_reports.json`. Free text never changes a listing.
- **Recommendation:** Yes, draft only.

### 20. A once-a-year reminder to re-read source terms

- **Benefit:** Give Food, IFAN, council pages, the Met Office and Natural Resources Wales can change their terms. A dated line asks Dean to re-read them, so a scrape that was fine in 2026 is not assumed fine in 2029.
- **Risk:** The reminder is ignored, or it is turned into an excuse to scrape more. It adds no URLs.
- **Effort:** S.
- **Conflict:** None.
- **Recommendation:** Yes.

### 21. Name a deputy, who still has to say yes in the files

- **Benefit:** If Dean is away, a named second person knows they can approve, and the queue of new places and closures does not sit forever.
- **Risk:** The system treats "a deputy exists" as a yes, and adds or removes a place on its own.
- **Effort:** S.
- **Conflict:** Automatic approval would break the hard rule. The deputy uses the same approved files Dean uses. An email is not a yes.
- **Recommendation:** Yes, as a written name only.

## Recommend no

### N1. Let a language model rewrite listing text

- **Benefit:** Wording might read more smoothly.
- **Risk:** The model invents a phone, an hour, or a closure, and it fights the memory of Dean's own wording.
- **Effort:** L.
- **Conflict:** Conflicts with "never invent data" and with learning from Dean's decisions, which only remembers wording and still asks every time.
- **Recommendation:** No.

### N2. Treat silence as a closure

- **Benefit:** A site that stops answering might be closed.
- **Risk:** A timeout, a redesign, or a rate limit removes a place people still need. A failed fetch is not a closure.
- **Effort:** S.
- **Conflict:** Conflicts with the closure rule and with "never invent". Confirmed closures already stay on the map until Dean agrees.
- **Recommendation:** No.

### N3. Add places from a feed that was only just spotted

- **Benefit:** New food banks would appear sooner.
- **Risk:** A wrong link becomes a pin, and the add-new-places guard is bypassed.
- **Effort:** M.
- **Conflict:** Breaks the hard rule. Item 5 flags the URL. This would publish it.
- **Recommendation:** No.

### N4. Move the clock times when the weather is bad

- **Benefit:** Cold-snap areas would be checked on an extra run.
- **Risk:** The published schedule changes, and the tests that lock the cron lines fail for a real reason.
- **Effort:** S.
- **Conflict:** Breaks the schedule rule. Cold snaps and weather warnings already move those councils earlier inside the next run that was already scheduled.
- **Recommendation:** No.

### N5. Scrape pages to invent benefit dates or school holidays

- **Benefit:** The demand forecast would fire on more days.
- **Risk:** A scraped sentence becomes a false payment date or a false holiday, and every food bank in the country moves up together.
- **Effort:** M.
- **Conflict:** Conflicts with "never invent". `scripts/holidays.py` already records that there is no single official UK school-holiday source. The forecast already accepts a file when that file names an http source and lists the dates. Type the dates from that source, or leave the file absent.
- **Recommendation:** No.

### N6. Train on visitor free text and change the map

- **Benefit:** "Report a problem" text might be classified automatically.
- **Risk:** The text can be wrong, hostile, or about a person. A model would write that onto a listing.
- **Effort:** L.
- **Conflict:** Conflicts with "never invent" and with the problem-report upgrade, which only raises priority after a person files the JSON.
- **Recommendation:** No.

### N7. Upgrade pinned dependencies on their own

- **Benefit:** A newer Playwright might parse more sites.
- **Risk:** A new version changes what is extracted, and the map moves with no human looking.
- **Effort:** S.
- **Conflict:** None with the wording of the hard rules, and still a bad idea next to item 3. Upgrade only when Dean asks, with the example pages from item 8 green before and after.
- **Recommendation:** No.

### N8. Guess a council from the postcode prefix

- **Benefit:** Stale-area and weather matching would cover postcodes missing from the cache.
- **Risk:** The wrong council moves up, including on a weather warning.
- **Effort:** S.
- **Conflict:** Conflicts with "never invent". A missing cache row stays "no effect".
- **Recommendation:** No.

### N9. Ignore robots.txt so the weekly floor is met

- **Benefit:** Every own-site page would still be fetched.
- **Risk:** The sweep fetches a page the site asked us not to fetch.
- **Effort:** S.
- **Conflict:** The weekly floor is about our schedule, not about permission. Item 14 is the allowed version.
- **Recommendation:** No.

### N10. Raise the boost cap, or drop the weekly floor, to make room for more signals

- **Benefit:** New signals would have more room to reorder the queue.
- **Risk:** One loud signal (a national cold warning, a national benefit date) swamps the others, or a failing site is left unchecked for more than a week.
- **Effort:** S.
- **Conflict:** Conflicts with the rules set for the 14 upgrades. New signals join the same cap.
- **Recommendation:** No.

### N11. Let the most-trusted source win a disagreement

- **Benefit:** Phone clashes would clear without Dean.
- **Risk:** A trusted source can still be wrong, and the pick is silent.
- **Effort:** S.
- **Conflict:** Conflicts with the conflict upgrade, which flags and never picks, and with change confidence, which can only refuse.
- **Recommendation:** No.

### N12. Remove a place because its source disappeared

- **Benefit:** The map would drop entries whose feed has gone.
- **Risk:** The place may still be open. The feed is not the place.
- **Effort:** S.
- **Conflict:** Breaks the hard rule. Item 2 flags the source. Dean decides.
- **Recommendation:** No.

## If only a few are built

Start with the small flags that cannot publish anything: 2 (source gone), 3 (pin report), 10 (London labels), 11 (override file check), 17 (cache gaps), 18 (weather key). Then the two memory limits, 7 and 13, before the files get large. Leave 9 (full replay) until the example pages in 8 exist.

Do not build any "recommend no" item to speed the others up.
