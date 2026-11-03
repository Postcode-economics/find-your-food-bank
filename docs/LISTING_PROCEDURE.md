# First-time listing procedure (rule 85, Dean 3 Nov 2026)

A first-time listing goes on complete and identical in format to established listings: every card field,
layout, icon, label, tag, hours and date format. Nothing verified is left off or added later. Missing information never blocks a listing: a place
with no stated hours (or wheelchair, facilities) is still listed and shows "Not stated"; whatever IS
verified at listing time goes on with it. The times
finder and its two-run check only monitor for later changes.

## Before a place is published (shelters, warm spaces, food banks)
1. **Approval**: id in `overrides/approved_new_places.json` (food banks: `foodbank_approved_new.json`).
2. **Verified record** (`overrides/<layer>_verified.json`): `evidence_url`, `quote`, `verified_on` (YYYY-MM-DD).
3. **Opening hours**: read on the place's own source (live, rendered, same URL, rule 27) and stored in
   `hours` (`opening_times` for food banks) with the exact wording in `day_time_quote` / `hours_quote`.
   The verification gate (`scripts/common.py verification_gate`) copies them onto the listing on its first
   run, and `scripts/hours_norm.py` puts them in the one standard format (rule 15). Only phone-line,
   office, referral-desk or other-service hours are not opening hours: leave `hours` empty so the card
   shows "Not stated". Never guess.
4. **Checked date**: `verified_on` / `last_verified` stored as YYYY-MM-DD; the card renders it in the one
   site format (rule 16, UK time).
5. **Type and icon** (shelters): `kind` is `hostel`, `day_centre`, `young_people`, or unset (standard
   hostel/night-shelter house icon). The same value drives the map pin, card icon and type label.
5b. **Pin matches the real type** (all layers). Required uniform layout for every donations-only food
   bank place (`kind` `warehouse` or `dropoff`: no collections or walk-ins), with no exceptions:
   - **Map pin**: `whIcon` in index.html: white rounded square (`#F2F4F8`) with a dark `#0A1628` outline
     and a dark down arrow. The same pin when selected (`select()` / `icFor()` via `nc()`); never the
     yellow walk-in/voucher food bank pin.
   - **Card**: the red-edged "Donations only" `ncb` banner with the box icon, name, address, then the
     "Get food at:" list of centres (or "Contact the food bank for where to get food."), same fields as
     every other warehouse card.
   - New listings get this automatically by setting `kind`; `tests/test_donation_pins.py` fails the build
     otherwise. Known locked variation: `b30-south-birmingham` shows a 📦 emoji in its label (wording
     locked by tests/test_labels.py). Pin design changes need Dean's OK first.
6. **Phone**: a verified number (`phone`, with `phone_source` where the number came from elsewhere); one
   tel: button, UK spacing.
7. **Who it's for / how to get in**: sourced `access` / `access_type` (referral only / open access tags),
   `groups` (who it's for).
8. **Wheelchair, facilities**: only when stated on the source; otherwise "Not stated".
9. **Source line**: `evidence_url` / `evidence_name` (or `source` + `source_url`).
10. **Welsh**: every row label comes from the shared card template, so Welsh text is identical.

## Tests that prove it
- `tests/test_first_listing_formats.py`
  - a new place with verified hours publishes them on its first run, already normalised;
  - every live shelter has a valid type, standard-format hours and ISO dates; warm-space hours standard;
  - browser parity: a new card has the same rows, labels, icon set, tel button, source link and
    "Last checked" date as an established card of the same type.
- Plus the existing design-lock, card-symbol and card-uniform tests.

## Backfill rule
When a gap is found on listings already live, audit every listing added in the last few days against
established listings of the same type, fill each gap from a verified source (own source read live,
quote stored), and leave "Not stated" only where the source genuinely gives none.
