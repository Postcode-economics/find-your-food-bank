
## v10 — two tiers + 3x-daily per-source recheck (21 Oct 2026)

**Tiers.** *Verified* = a credible source states the day and time. *Unverified* = confirmed operating some other way (a 2026 sign of life, or a current listing). These get the badge "Unverified – call before you go" / "Heb ei wirio – ffoniwch cyn mynd", a grey pin, and a "Seen open: <domain>, <date>" line. Every list has a "Verified only" filter. Referral-only shelters get a "Referral only" chip; they are never presented as open-access.

**Totals after the first live recheck** (postcodes.io nation lookup):
- Shelters: 94 = 64 verified (Eng 38, NI 19, Scot 4, Wales 3) + 30 unverified (Eng 19, NI 3, Scot 4, Wales 4). Access: 68 referral-only, 22 self-referral, 4 open-access.
- Warm spaces: 158 = 92 verified (Eng 90, Scot 2) + 66 unverified (Eng 62, NI 1, Scot 2, Wales 1).

**Per-run checks** (`scripts/recheck.py`, run inside `verification_gate` on every build; any failure means the entry is omitted that run and logged to pending):
1. **HTTP:** the page is fetched fresh with redirects followed. Anything other than a 200, or under 200 chars of text, counts as unreachable. Each failed page gets one sequential retry.
2. **Redirect cross-check:** the final URL host must equal the claimed host.
3. **Content:** the page must still name the place. If the entry has a quoted time or day, it must still appear. Closed or ended wording fails the entry.
4. **Schema:** name; UK lat/lng; postcode format; address; hours day keys and `HH:MM - HH:MM`; access_type enum; referral_only must state a referral; ended is boolean; not flagged closed.
5. **Change detection:** the sha256 of the text, the ETag and Last-Modified are stored and compared with the last run (`changed_since_last_run`, `headers_changed`).
6. Tier-2 warm spaces whose only sign is their Warm Welcome listing are checked against that run's freshly downloaded feed.

Each entry stores its url, fetched_at, http, final_url, hashes and extracted values in `logs/<layer>_recheck.json`. Nothing is carried over from the previous run.

**Publish guard:** `scripts/verify_fresh.py <layer>` exits 1 if the log is missing or more than 2h old, or if any published entry lacks an ok recheck with a matching fetched_at. Both workflows run at 04/12/20 UTC in this order: unit tests, build, guard, commit. Tests are in `tests/test_recheck.py` (11 cases). Caveat: a repo admin can still disable Actions; the guard blocks publishing, not that.
