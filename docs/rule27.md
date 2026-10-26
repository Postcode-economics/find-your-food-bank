# Rule 27 — live opening times

Effective 26 Oct 2026. This applies to the opening-times audit and to the three-times-daily refresh sweep (`scripts/full_check.py` and the source-page check in `scripts/discover.py`).

For each food-bank listing that shows a source URL:

1. Read the live page only. A saved, cached, archived, or previous-run copy is not a source. If the live page does not open, the listing is unclear and the hours already on the card stay as they are. They are not marked verified.
2. The URL that was read must be the source URL the listing shows. `http` to `https`, a leading `www`, and a trailing slash are the same page. A different host, path, or query is a different page. A cache, archive, amp, or `cdn-cgi` address is a cached variant. Any of those is unclear, and the body of that other page is not used.
3. Fetch the HTML first, politely (one request at a time to a host, then a 2 second gap; the shared Trussell server stays capped as before). If that HTML does not already contain a complete day and time set for this postcode, render the same URL in a headless browser, with scripts, and wait for the page to load. A plain fetch can miss times that a script adds. If the browser cannot run, the listing is unclear. It is not verified from the incomplete HTML.
4. A listing is verified only when every open day and every clock time recorded on the card appears on that rendered page, and every open day the page lists for this postcode is in that record (a Monday–Friday range counts as each day in the range). Store a short quote copied from the page. The quote is the evidence.
5. A failed open, a redirect, a mismatch, a skipped site, or anything else that cannot be confirmed goes on the unclear list. The line for that listing is: Opening times not listed. Call before you go. Nothing is guessed, and the previous run's hours hash is not carried forward as a verified reading.

Access flips, phone fixes, and closure notes still need the same result on two runs before they are applied. Those checks are unchanged. This rule does not auto-apply a new timetable from the sweep; it stops a stale reading from being treated as confirmed.
