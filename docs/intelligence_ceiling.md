# How intelligent the sweeps can realistically be

Owner: Dean. Written 25 October 2026, after the 14 sweep upgrades and proposals 1–20. Proposal 21 and the "Recommend no" list in `docs/future_proofing_proposals.md` are not built, and this note does not build them.

**Answer:** No. The queue-scoring part is close to as intelligent as it can usefully be. More weights will not make the map more true. What is still missing is facts the scorer never sees, parsers that break when a page changes, and one person's time to say yes or no.

The hard rules still apply to every idea below. Nothing here may invent a phone, an hour, a date, or a council. Nothing may add or remove a place. You approve changes in the files, the same way as now. The clock times stay put. The weekly floor stays 7 days. The shared boost cap stays 3.0. A disagreement is flagged and never picked.

## What is already about as good as this design gets

The sweeps already decide order, frequency inside a scheduled run, and whether to try plain HTTP or HTTPS first. They fade old results, remember how often a place changes, move up a hand correction, a problem report, a stale area, a named weather warning, and a cold snap. They hold an automatic edit back when two sources already disagree. They stop a run that would change far more places than usual. They flag an empty parse, a source that failed three times, a robots.txt disallow, and a shrunken hand file. They do not publish a new place or take a pin off the map.

That is the right shape. A further formula on top of the same files will mostly reshuffle the same queue. Several of the signals are already dark because the file they read does not exist yet: visitor numbers (`reports/demand.json`), visitor reports, benefit dates, and school holidays. The season boost has almost no history, because the change log only starts in October 2026. Turning those weights up would be turning up a zero.

The Sunday grade has a second limit. A "find" is a flag or an automatic edit on that run, not a later yes from you. A signal that flags too much can look successful. Grading it harder will not create a truth the run never recorded.

Freshness has a hard stop that is not a bug. A place is guaranteed a look at least every seven days, inside runs that were already scheduled. A wrong phone or a closure can sit until the next of those runs. The rules forbid an extra run when the weather is bad. Inside that clock, reordering is the whole of what "smarter" can mean.

## The biggest remaining gaps

1. **You are the limit.** New places, permanent closures, phone clashes, empty parses, and dead sources all wait on `reports/pending_dean.md` and the hand files. The sweeps can raise flags faster than one person can clear them. A smarter score that produces more flags, without making each decision shorter, makes the map wait longer.

2. **A redesigned page is not understood.** Self-heal only switches a fetch between HTTP and HTTPS for a site that already worked one of those ways. It does not read a new page layout. An empty parse flags that. The hours and phone then stay as they were until someone changes the parser. The small example pages protect the parsers we already have. They do not teach a parser a layout it has never seen.

3. **The only clash the system notices is the phone.** Stored phone against the place's own site is flagged, and nothing is picked. Opening hours, voucher or walk-in, and address can disagree between Give Food, IFAN, and the own site, and that disagreement is not a conflict row. Those are the facts someone travels with.

4. **Several "smart" inputs are empty on purpose.** There is no visitor-number export, no typed benefit calendar, and no school-holiday file, because there is no single official UK holiday list and because a scraped sentence would be an invented date. Weather and stale-area matching also skip any food-bank postcode with no row in `overrides/district_cache.json`. The gap is counted. It is not filled. Until those facts exist as real files, the matching signals do nothing, which is correct and also a real hole.

5. **A robots.txt disallow leaves the hours unchecked.** The page is not fetched, the hours are not guessed, and the place stays. There is no next step that says "the own site cannot be read, and the directory hours on file were not checked against it." The old hours can sit there looking ordinary.

6. **The automatic-edit log covers two of the seven automatic kinds.** A voucher or walk-in flip and one clear new phone write the rule, the confidence, and the source URL. Opening times, a temporary closure, a warm-space end date, SWEP open or close, and a moved link to the same organisation do not yet write that line. The rules file still decides. The record is incomplete.

7. **The morning note got longer than the decision.** Each new safeguard added a sentence. The sentences are true. They are a poor list of what to do first on a weekday morning.

## Further ideas

Effort is the same scale as the proposals: **S** one small change with a test, **M** a few files and tests, **L** a new store or a long harness. Value is judged by whether a listing becomes true sooner, or a wrong automatic edit is caught, under the hard rules.

### Worth doing

#### 1. One decision list, oldest first

- **Value:** The flags already exist. What is missing is a single list of rows that need a yes or a no: new place, closure, phone clash, empty parse, source gone. One row, the source URL, how many days it has waited. You still approve in the same files.
- **Risk:** A short list hides a hard case, or sorts a closure under a cosmetic flag. Oldest-waiting and "this would take a pin off the map" have to stay at the top even when other scores are louder.
- **Effort:** M.
- **Worth doing.** This is the change most likely to make the map truer. It adds no data and publishes nothing.

#### 2. Measure days from first flag to your decision

- **Value:** When you accept a phone, a closure, or a new place, record the date of the first flag and the date you wrote the file. That is the only honest measure of whether reordering caught the change sooner. It uses your files and the existing logs. It invents no outcome.
- **Risk:** A handful of decisions will look like a trend. The note should show the count beside the average, and say nothing when the count is small.
- **Effort:** S.
- **Worth doing.** Without it, further scoring is guesswork about guesswork.

#### 3. Flag hours and access clashes the same way as phones

- **Value:** When the own-site extract and the stored hours, or the stored voucher/walk-in tag, already disagree, flag the row and pick nothing. Same rule as the phone conflict. No new fetch.
- **Risk:** A directory that is merely a week behind will flag a lot. Show it only when both sides are non-empty extracts from this run or the last stored check. A missing side stays "no effect".
- **Effort:** M.
- **Worth doing.** Phone-only conflicts miss the facts that send someone to a closed door.

#### 4. One flag when many sites of the same template parse empty

- **Value:** Forty Trussell pages that all return HTTP 200 and extract nothing are one broken template, not forty mysteries. Group empty parses that share a host pattern already known to the code, and still list the count.
- **Risk:** The group hides one site that is honestly empty this week. Keep the individual rows one click away, and do not clear them.
- **Effort:** M.
- **Worth doing.** It points the parser work at the break, which is the actual repair self-heal cannot do.

#### 5. Say when robots.txt left the hours unchecked

- **Value:** The morning note names the place, says the own site was not read, and says the hours were not guessed. If a directory hour is already stored, the note says it was not checked against the own site. It does not copy that hour onto the card.
- **Risk:** A reader treats the directory hour as confirmed. The sentence has to forbid that, and the code must not write `opening_times`.
- **Effort:** S.
- **Worth doing.** It stops a blocked page from looking the same as a page we read.

#### 6. Finish the automatic-edit log for the other five kinds

- **Value:** Opening times, temporary closures, warm-space end dates, SWEP open or close, and a moved link get the same line already kept for a voucher flip and a clear phone: rule name, confidence, source URL, and `decides: false`.
- **Risk:** The log is mistaken for a new source of truth. It stays a log. A kind the rules refuse still writes nothing.
- **Effort:** S.
- **Worth doing.** This finishes a record that was approved. It is not a new kind of intelligence.

#### 7. Look up missing councils only for postcodes already on a listing

- **Value:** Weather warnings and stale-area order skip every food-bank postcode with no row in `overrides/district_cache.json`. A slow lookup of `admin_district` from postcodes.io, for a postcode that is already on a published listing, fills that row with a real answer. A failed or empty answer stays a gap. The existing rate-limit pause still applies. Nothing is guessed from the postcode letters.
- **Risk:** A bad postcode on the listing becomes a bad council and moves the wrong area up. Store the raw postcode beside the district, and do not invent a district when the API returns none. Do not run this from the gap report itself; that report stays a count.
- **Effort:** M.
- **Worth doing, after the decision list.** It is the one data gap that has an official answer sitting behind an API we already use elsewhere. It is not the rejected idea of guessing a council from the prefix.

#### 8. Let a repeated "no" sink in the queue only

- **Value:** When you have rejected the same kind of flag for the same site more than once, that kind waits behind flags you have not answered. The listing does not change. A later flag of a different kind, or a closure, is not sunk.
- **Risk:** A past no hides a real change of the same kind. Cap it at sort order. Never auto-dismiss. A closure is never sunk by an old no.
- **Effort:** M.
- **Worth doing only in that narrow form.** Wider than that, it becomes a silent veto, which the rules forbid.

### Do these as files, not as new code

The demand weight, the visitor-report weight, and the benefit-date forecast already read a file and do nothing when the file is absent. Writing more maths for them will not help.

- A real export of our own visitor counts, in the shape `reports/demand.json` already expects, turns the demand weight on. That export is an operations step.
- Benefit dates help only if you type them from a named http source into the file the forecast already accepts.
- School holidays stay unused until there is one official UK list. Scraping a council sentence into a national date is the rejected idea, and it would move every food bank together.

### Overkill

These would feel intelligent and would not make a listing truer, or they would break a rule to try.

| Idea | Why it is overkill |
|---|---|
| Another learned weight, a second cap, or a bandit over the signals | The shared cap is already the limit. Most added signals have no facts behind them. A new weight competes with the weekly floor and the signals that do have facts. |
| A model that extracts hours or phones from page text | It will invent a digit. The rejected list already covers a model rewriting listings, and training on visitor free text. The example pages are for catching a human parser change, not for training one. |
| A model that summarises the morning note | It can drop the one row that needed a decision. A shorter decision list is the version that keeps every row. |
| Saving full page HTML so a future parser can replay it | Already refused. The replay store keeps the extracted fields. Full pages are someone else's site, kept forever. |
| Treating a silent site, a missing feed, or a Companies House row as a closure | A failed fetch is not a closure. The pin stays until you say so. |
| An extra scheduled run on a cold day | The clock is locked. Those councils already move up inside the next run that was going to happen. |
| Letting the trusted source win a phone or hours clash | A trusted source is sometimes wrong. The clash stays a flag. |
| Upgrading Playwright on a timer so more sites parse | A new browser build changes what is extracted, with nobody looking. Upgrade when you ask, with the example pages green before and after. |
| Ignoring robots.txt so the weekly check still "sees" the page | The weekly floor is our schedule. It is not permission. |
| Auto-approval because a deputy is named, or because an email said yes | Not approved. A second person, if you ever name one, uses the same files you use. Software must not treat that name as a yes. |
| Checking all ~1,060 sites on every run so the score matters less | The time budget and the polite gaps are what keep the sweeps welcome. Order exists because everything cannot be first. |

## What not to do next

Do not add a twenty-first signal to the boost. Do not raise the cap. Do not let the system publish a place, remove a place, or pick a value because the queue is long.

If one thing is built from this note, build the decision list, and beside it the count of days from first flag to your answer. Those two show whether the sweeps are actually getting a true listing onto the map sooner. Everything else in the "worth doing" list is smaller than that, and everything in the overkill list should stay unbuilt.
