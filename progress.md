# National sweep progress (updated 21 Oct 2026, 16:20 BST)

DuckDuckGo blocked automated queries after 41 councils (HTTP 202 'anomaly' page). The sweep switched to each council's own sitemap (robots.txt / sitemap.xml), matching URLs that contain warm space, warm hub, warm welcome, SWEP, severe weather, cold weather, night shelter, rough sleeping or emergency accommodation. Every hit was fetched and parsed.

| Nation | Councils | Search done (DDG) | Sitemap tried | Sitemap had relevant URLs | Councils with a relevant page fetched | Venue directories used |
|---|---|---|---|---|---|---|
| England | 317 | 56 | 283 | 82 | 108 | Havering (8 verified) |
| Scotland | 32 | 5 | 32 | 9 | 11 | East Lothian (6 unverified) |
| Wales | 22 | 7 | 22 | 8 | 11 | Carmarthenshire (16 unverified) |
| Northern Ireland | 11 | 5 | 11 | 3 | 6 | none |

Stage 2 parsed 1,005 candidate URLs; 867 were fetched OK and 528 were relevant (136 councils). Only 7 pages were clearly dated to the 2026-27 season and listed venues. Most council warm space pages link to the Warm Welcome map (already the base layer) or only advertise grants. SWEP pages give phone numbers, not shelter addresses.

Directories found but not used (no date on the page, so no 2026 sign of life): Bexley, Bedford (local offer), West Dunbartonshire, Aberdeenshire, Blaenau Gwent. Brentwood: last updated 28 Jan 2025 (stale). Arun: news archive (old season).

Charities (15): checked, with these results.
- Done: St Mungo's (NSNO hubs are referral-only with no public addresses; hostels are referral-only). Simon Community Scotland (hubs are day centres; women's emergency accommodation addresses are not public). Depaul (Nightstop uses host homes, so nothing to pin; the London Youth Hub has no public address). Emmaus (long-term supported housing, so excluded like move-on accommodation). Framework (the Street Outreach Team is the route in, phone 0800 066 5356; Emmanuel House Night Shelter is referral-only, via Framework). NIHE (self-referral hostel list: nihe.gov.uk returns 403 to automated fetches, and the Housing Rights copy is a June 2025 PDF, so these cannot pass the live re-check). Housing Justice (rotating church winter shelters, no fixed site; no 2026-27 list published).
- Not yet: Shelter, Crisis, Centrepoint, YMCA, Riverside, Llamau, Shelter Cymru, Turning Point Scotland.

Other sources still to do: Homeless Link 'Find help' hostel search (JS app), Powys warm spaces directory (JS), Causeway Coast and Glens warm welcome directory (NI; Dec 2022 interactive map, so not current), Open Innovations warm spaces aggregator, CofE/Methodist lists.

**Resume from:** the remaining charities above, then the other sources. Councils without a sitemap or with no relevant URLs could be retried with the WebSearch tool, one council per query.

## Checkpoint 21 Oct 2026 16:27 (paused by Dean)
Commits on copy branch: 2bef41d (batch 2: Open Innovations directories), a392284 (batch 3: Homeless Link + 2026 corroboration).
- Batch 2: +21 verified warm spaces from Voluntary Action Islington (page maintained for winter 2026-27), +25 unverified from Southwark Council page (updated 2 Oct 2026; entries with past end dates dropped). 17 Southwark and 5 VAI listings were already on the map and were not added again.
- Batch 3: +1 verified shelter (Harrogate Homeless Project) and +6 unverified shelters (Signposts SOS Luton, King's Lynn Night Shelter, New Hope Sanctuary Watford [referral_only], DENS The Elms [referral_only], YMCA Nomad Centre Lincoln, St Anne's Birmingham). All pass the live re-check.
- Charities: Crisis (Skylights are day centres), Centrepoint (referral only, no public addresses), Llamau (helpline/Nightstop), Riverside (supported housing; The Crossings Hull not corroborated), Turning Point Scotland (crisis unit, not a shelter). Shelter and Shelter Cymru are advice only and signpost to Homeless Link.
- Blocked from the box: Powys directory (403), The Pavement (timeout), NIHE (403).
- Totals: shelters 102 (66 verified, 36 unverified); warm spaces 235 (122 verified, 113 unverified). These counts move slightly between runs as sources fail or recover.
RESUME HERE:
1. batch_patterns/probe.py (URL-pattern probe of the councils whose sitemaps had no hits) was killed mid-run with no output. Rerun it in the background.
2. Homeless Link candidates not yet corroborated, listed in batch_hl/cands.json: The Crossings Hull, Leyland Road Southport, Nightsafe Blackburn, St George's Crypt Leeds.
3. OI directories still to check per venue: Cambs ACRE, Camden, Argyll TSI, Communities 1st, Rugby, Fylde, B&NES, Chelmsford.
4. Emmanuel House Nottingham (referral_only): needs a source the re-check can fetch.
5. CofE and Methodist lists not started.
