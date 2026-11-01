# Shelter batch hand-check applied (1 Nov 2026, Grok Bot)

Dean hand-check of 197 rows added since `1857e7a08` → `5a306e518`. This file records **only the rows changed** in PR (not a full re-audit table).

## PULL (5) — `overrides/shelter_exclusions.json` + removed from `shelters_verified.json`

| id | reason |
|---|---|
| `man-google-maggs-day-centre-worcester` | Duplicate of `man-maggs-day-centre-worcester` |
| `man-google-share-homeless-action-centre-shac` | Duplicate of `man-share-homeless-action-centre-chester` |
| `hl-ymca-lincs-nomad-centre` | Duplicate of `man-nomad-centre-ymca-lincolnshire` |
| `man-vaughan-house` | Alcohol detox unit, not a shelter |
| `ss-63bf328f843d85a21d7bbdce` | No such service on New Start own page |

## FIX (6)

| id | change |
|---|---|
| `man-google-day-centre` | Name → **Whitechapel Mission Day Centre** |
| `hl-st-georges-crypt-leeds` | Phone **0113 245 9061**; evidence **https://stgeorgescrypt.org.uk/contact** |
| `man-bht-phase-one` | Referral line: council Housing Advice **01273 294400 option 1** |
| `man-aberdeen-cyrenians-direct-access` | Name → **Aberdeen Cyrenians**; day centre kept (weareac.org Direct Access drop-in at 62 Summer Street AB10 1SD) |
| `man-streetlife-the-base-young-people-16-25` | Type → **young_people** (16–25 night shelter) |
| `man-doorway-young-people-16-25` | Type → **young_people** (16–25) |

Expected published count on this branch (from main 333): **328** (= 333 − 5 pulls). If merged after PR #376 shelter set (306 rows), expect **301** (= 306 − 5).
