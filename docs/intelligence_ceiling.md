# How intelligent the sweeps can realistically be

Owner: Dean. Written 25 October 2026, after the 14 sweep upgrades and proposals 1–20. Proposal 21 and the "Recommend no" list in `docs/future_proofing_proposals.md` are not built, and this note does not build them.

**Answer:** The queue score is close to as useful as it can be. More weights will not make the map more true. That is not the furthest system worth designing.

The furthest system, the one worth calling super-intelligent for this job, reads every source it is allowed to read, quotes every fact it keeps, lays every source side by side, predicts a change only when a real date or a repeated history says so, explains each row, and gets better at proposing after you say yes or no. It still does not invent a fact, and it still does not change the live site except through the guards that already exist.

The hard rules apply to every stage below. Nothing may invent a phone, an hour, a date, or a council. You approve a new place or a removal in the files, the same way as now. An automatic edit still has to pass `overrides/auto_apply_rules.json`, the two-run confirmation, the confidence hold, the anomaly brake, the publish gate, and the refresh guard. The clock times stay put. The weekly floor stays 7 days. The shared boost cap stays 3.0. When sources disagree, the result is an open row. Nothing is picked.

## What is already about as good as this design gets

The sweeps already decide order, frequency inside a scheduled run, and whether to try plain HTTP or HTTPS first. They fade old results, remember how often a place changes, move up a hand correction, a problem report, a stale area, a named weather warning, and a cold snap. They hold an automatic edit back when two sources already disagree. They stop a run that would change far more places than usual. They flag an empty parse, a source that failed three times, a robots.txt disallow, and a shrunken hand file. They do not publish a new place or take a pin off the map.

That is the right shape. A further formula on top of the same files will mostly reshuffle the same queue. Several of the signals are already dark because the file they read does not exist yet: visitor numbers (`reports/demand.json`), visitor reports, benefit dates, and school holidays. The season boost has almost no history, because the change log only starts in October 2026. Turning those weights up would be turning up a zero.

The Sunday grade has a second limit. A "find" is a flag or an automatic edit on that run, not a later yes from you. A signal that flags too much can look successful. Grading it harder will not create a truth the run never recorded.

Freshness has a hard stop that is not a bug. A place is guaranteed a look at least every seven days, inside runs that were already scheduled. A wrong phone or a closure can sit until the next of those runs. The rules forbid an extra run when the weather is bad. Inside that clock, reordering is the whole of what the score can do. Reading, reconciling, and predicting, in the roadmap below, still spend those same runs.

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
| A model that writes a listing, or fills a field it cannot quote from text we actually fetched | That is an invented digit. Stage B below is the allowed version: a reader that proposes a field only when the value is a substring of the fetched text, in shadow first, and that never writes the live file itself. |
| A summary that can drop a row from the morning note | The explanation in Stage E keeps every decision. A paraphrase that omits one is a lost closure. |
| Saving full page HTML so a future parser can replay it | Already refused. The replay store keeps the extracted fields. Full pages are someone else's site, kept forever. |
| Treating a silent site, a missing feed, or a Companies House row as a closure | A failed fetch is not a closure. The pin stays until you say so. |
| An extra scheduled run on a cold day | The clock is locked. Those councils already move up inside the next run that was going to happen. |
| Letting the trusted source win a phone or hours clash | A trusted source is sometimes wrong. The clash stays a flag. |
| Upgrading Playwright on a timer so more sites parse | A new browser build changes what is extracted, with nobody looking. Upgrade when you ask, with the example pages green before and after. |
| Ignoring robots.txt so the weekly check still "sees" the page | The weekly floor is our schedule. It is not permission. |
| Auto-approval because a deputy is named, or because an email said yes | Not approved. A second person, if you ever name one, uses the same files you use. Software must not treat that name as a yes. |
| Checking all ~1,060 sites on every run so the score matters less | The time budget and the polite gaps are what keep the sweeps welcome. Order exists because everything cannot be first. |

## What not to do next

Do not add a twenty-first signal to the boost. Do not raise the cap. Do not let the system publish a place, remove a place, or pick a value because the queue is long. Do not skip to a reader that writes the live site.

If one thing is built first, build the decision list, and beside it the count of days from first flag to your answer. That is Stage A. The quoted reader, the ledger, the predictions, and the self-improvement loop come after it, in that order, each one still unable to apply itself.

## The most capable sweep system

This is the end state the rules allow. It is ambitious on purpose. It is also a machine that works from evidence, so it is not a mind that knows a food bank better than the pages do.

On a weekday morning it has already done six things.

1. **It has read.** For every food bank, shelter, warm space, council page, and official feed it is allowed to fetch, it has tried to pull out phone, hours, access, closure wording, end date, and a moved link. A page it has never been given a hand-written parser for is still readable. Each kept value is a substring of the text that was fetched on that run. A value with no quote is dropped. A page disallowed by robots.txt is not read. A host that is not on the official list is flagged, not fetched. A missing API key is reported, and no area is invented to fill it.

2. **It has reconciled.** Every place has a ledger: one row per field per source, with the quote, the URL, and the time. The proposed card is filled in only where the non-empty sources agree, or where an edit is already on the automatic list and has been seen twice. A clash stays open, with every value shown and `chosen` empty. Give Food, IFAN, the own site, a council page, and a hand file are all just sources in that ledger. None of them wins because it is trusted.

3. **It has predicted.** Some changes are visible before the day they happen, because somebody has already written the date, or because this place has already changed on a measured rhythm. The system moves that place to the front of the next run that was already going to happen, and it says why. It does not mark the place closed. A prediction with no date, no quote, and no two observed gaps is not emitted.

4. **It has explained.** Each row you see is a short argument: what was read, the quote, what was refused, which rule would allow an automatic edit, what would change on the live site if the guards passed, and how often you have agreed with this kind of row. The argument is the record. It does not decide.

5. **It has held the line.** New places and removals wait in the files you already approve. Automatic edits still pass the rules, the two-run check, the confidence hold, the anomaly brake, the publish gate, and the refresh guard. A candidate reader that has not beaten the current one on the example pages does not run in the publishing path.

6. **It has improved.** Your yes and your no are the labels. A reader or a predictor you reject more often than you accept is turned down. A candidate replacement is scored offline against the example pages and against your past corrections. It replaces the current reader only as a code change you can review. Overnight it writes what it got wrong, by source and by extractor. It does not edit the rules file, the clock, or the live data files by itself.

What this achieves, when the stages below are real, is a sweep that notices an announced closure before the morning it happens, reads a council page it has never seen, shows you every source instead of hiding a clash, tells you why the row is in front of you, and gets quieter at the kinds of proposal you keep refusing. The live map changes only when the guards that exist today say it may.

## Roadmap

Each stage is usable on its own. A later stage does not turn an earlier guard off. Effort is **S** one small change with a test, **M** a few files and tests, **L** a new store or a long offline harness.

### Stage A. A queue a person can finish, and a clock on each decision

This is the "worth doing" list above, and it is the foundation. The flags already exist. They become one list: new place, closure, phone clash, empty parse, source gone, oldest first, with a closure kept at the top. Beside it, the days from the first flag to the date you wrote the hand file.

**What it really achieves.** You can clear a morning, and you can see whether any later cleverness made a true change reach the map sooner. Until this number exists, a smarter reader has nothing honest to learn from.

**Risk.** A short list hides a hard case. The days-to-decision average lies when the count is small, so the count is shown beside it.

**Effort.** M for the list, S for the clock.

### Stage B. A reader that quotes, in shadow

A second reader runs beside the hand-written parsers. It may be a stricter set of patterns, or a model, provided the contract is the same: output a field only when the characters of the value appear in the fetched text. The quote stored is that short span, not the page. For a run of weeks it writes a shadow file and changes nothing that is published. Each morning compares shadow against the current parser and, later, against your corrections.

**What it really achieves.** A redesigned page, and a council page with no parser yet, can produce a proposal with evidence. The current parsers keep publishing. You see the shadow's misses before it is allowed near an automatic edit.

**Risk.** A quote can be real text and still be the wrong fact: the funder's phone in the footer, last year's hours in a news item, "closed" inside "we are not closed". Shadow mode is how that shows up. A model that paraphrases instead of quoting will invent a digit; that output fails the contract and is dropped. Storing the whole page is still refused.

**Effort.** L.

### Stage C. A ledger, and reconciliation that knows when it does not know

The shadow fields, the current extracts, the feeds, and the hand files go into one ledger per place. The proposed value for a field is set only when every non-empty source agrees, or when the existing automatic rule already allows that kind of edit after two runs. Otherwise the field is unresolved and becomes a decision row. Trust never breaks the tie.

**What it really achieves.** Hours, access, and address clashes become visible the way phone clashes already are. Agreement can flow through the guards that already exist. Disagreement waits for you, with the values side by side.

**Risk.** Early on, almost everything is unresolved, and the decision list gets longer. Stage A has to be in place first, or the ledger buries you. A blank source must not count as agreement.

**Effort.** L.

### Stage D. Prediction from dated evidence only

The predictor emits "likely to change" or "likely to close" only from evidence already in hand:

- a scheme end date, or a quoted sentence that names a future date ("last session 1 December", "closed from Monday");
- a change rhythm computed after two observed gaps, which the learning record already knows how to store;
- a week of year that has been busier in at least two past years of the real change tally;
- a cluster of real changes already seen this week at other places in the same council, used only to move the remaining places up.

The effect is order inside the next scheduled run, plus a row on the decision list when the date is close. The place stays open on the map until a closure is confirmed the way it is today. No evidence of that kind means no prediction. Silence, a failed fetch, and a vanished feed are not predictions.

**What it really achieves.** The check happens on the run before a known date, and you see the announcement with its quote before the morning people turn up and find the door shut. Seasonal intelligence starts only once two years of real tallies exist, which is the rule already written down.

**Risk.** A quoted date can be last year's poster. The year has to be in the quote, as the warm-space end-date parser already requires. A rhythm can fire on a place that changed twice for unrelated reasons. The prediction moves a check forward. It must not write `closed`.

**Effort.** M once the ledger and the tally exist. The rhythm and the season code are partly there; the missing piece is the quoted future date and the rule that refuses a prediction with no evidence.

### Stage E. An explanation on every row

The morning note's decision rows become the argument from Stage C and Stage D: sources, quotes, the rule, the refusals (robots, empty parse, low confidence, anomaly brake, missing district), and the sentence "if you say yes, the card changes from X to Y" or "this would not change the card". How often you have agreed with this kind of row is shown once the Stage A clock has a history. Nothing is omitted to make the note shorter. The decision list is the shortening.

**What it really achieves.** You can approve or refuse without opening the page first, and you can see when the system is unsure. A later audit can replay the argument from the quotes and the ledger without the original HTML.

**Risk.** A fluent sentence that is not tied to a quote will be trusted too quickly. The sentence is generated from the ledger fields. A row with no quote does not get a smooth explanation; it gets "no quote, no effect".

**Effort.** M.

### Stage F. A loop that improves the reader and the predictor

The labels are your yes, your no, and any later hand correction. Once a week the system reports, for each reader and each predictor, how many proposals you accepted and how many you refused. One you refuse more often than you accept is turned down, the same way a weak signal is already turned down on Sunday, and it is never turned up by this grade.

A candidate reader is scored offline on the example pages plus every field you have corrected. It can replace the publishing reader only as a reviewed code change, and only when it is at least as good on that set and it does not increase fields that fail the quote check. The previous reader stays so the change can be reverted. The candidate does not edit `auto_apply_rules.json`, the workflows, or the live data files.

**What it really achieves.** The system gets better at the proposals you keep confirming, and it gets quieter at the ones you keep rejecting, without a person rewriting a parser for every new council template. A bad candidate cannot reach the site by itself.

**Risk.** It will copy a past yes that was wrong, and then defend it. You need a way to mark a past yes as a mistake, or the golden set freezes the error. It will also under-flag a new kind of change that looks like an old refusal. A closure is never turned down by this loop. With few decisions the grade says "not enough" and changes nothing, which is the same honesty the Sunday grade already uses.

**Effort.** L.

## Limits that stay, however far this is built

- **No written evidence, no knowledge.** A closure, a new phone, or a new site that exists only because someone knows it is invisible. Predicting it would be inventing it.
- **Some sources stay unread.** A scan with no text, a login wall, a robots.txt disallow, a missing weather key, and a host that is not on the official list do not become facts. The place stays on the map. The gap is named.
- **Disagreement is a finished result.** The super-intelligent act, when two real sources differ, is to show both and wait. Picking the trusted one is the failure.
- **The clock does not become intelligent.** Prediction spends attention inside the next run that was already scheduled. It does not add a run, and a quiet place is still guaranteed only a weekly look.
- **A true quote can still be the wrong fact.** Footer phones, old news, and "we are not closed" will get through a quote check. Shadow mode, two-run confirmation, and your approval are the backstop. The reader does not get a wider automatic list than the rules file has today.
- **Self-improvement is only as good as your labels.** Few decisions, or a wrong yes left in the set, and the loop should change nothing. It must say so.
- **"Any source" still means the sources whose terms you have accepted.** The yearly reminder stays. A newly spotted feed is flagged. It is not added to the map and it is not scraped just because the reader could read it.
- **This ceiling is an evidence machine.** It can be earlier, broader, and clearer than the sweeps are today. It cannot be more true than the pages, the feeds, and your decisions.
