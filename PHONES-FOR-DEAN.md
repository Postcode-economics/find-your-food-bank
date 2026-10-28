# Phone numbers held for Dean (listings batch #239, 28 Oct 2026)

Dean's rule (28 Oct 07:02): phone changes that the organisation's own website confirms (identical on 2 reads, no conflicting own page) are applied without waiting. Every candidate was re-read by scripts/verify_own_page.py (PR #245); AUTO_APPLY rows were applied with an undo entry in logs/listings_batch_28oct.json. Only the rows below are held.

## Held

| Listing | Current (shown) | Proposed | Own-page URL | Exact quote | Why held |
|---|---|---|---|---|---|
| `micah-liverpool` Micah Liverpool Foodbank | 01517027206 | 07398017435 | https://micahliverpool.com/contact/ | NOT CONFIRMED on own page - own page blocked (bot check) on 3 reads | site down: own page could not be read (verifier and 3 earlier reads) |
| `kinmel-bay-church` Kinmel Bay Church Foodbank | 07841678889 | 07885696522 | https://kinmelbaychurch.org.uk/food-bank-2/ | "l Bay Church Foodbank is Open Tuesday and Friday 11 am – 1 pm phone – 07885696522        YOU CAN ALSO HELP BY D" (found on reads r2,r3) | verifier REVIEW: number not on both reads |
| `st-philips` St Philip's Foodbank | 07396614430 | 07929733555 | https://www.nnetwork.org.uk/news/st-philips-food-bank-service/ | "f you need a food parcel to be delivered to your home, please contact 07929733555 by text by Wednesday evening" (found on reads r2,r3) | source is a news post on nnetwork.org.uk, not the food bank's own site |
| `portsmouth/paulsgrove` Paulsgrove | 02392385047 | 02392987976 | https://portsmouth.foodbank.org.uk/about/ | "re Somers Road Southsea PO5 4QA  e: foodbank@hopeportsmouth.church t: 02392987976 or 07720344130   FAQs   Donat" (found on reads r1,r2,r3) | own pages conflict: the Portsmouth Foodbank locations page still shows 023 9238 5047 on the Paulsgrove card; the proposed 023 9298 7976 is the general line on the about page |
| `ww-65437319` Lambourn Lunch Club | 07564 984210 | 07770 394123 | https://lambournjunction.uk/lambourn-lunch-club/ | "please contact Helen at 07770 394 123 to reserve your place" (verifier, both reads) | named volunteer's mobile (privacy): not applied |
| `highland/dingwall` Dingwall | 07884869020 | 01463 715615 (fault scan) | https://newstarthighland.org/how-we-help/highland-foodbank | page showed no number on either read | verifier REVIEW: no number on the page |
| `ww-67300210` Refreshment Stop | 0121 820 6782 | 07398 187780 (fault scan) | https://www.theelitechurch.org/service-page/refreshment-stop-place-of-welcome | page shows no number | verifier REVIEW: no number on the page |

## Kept, needs Dean to confirm

| Listing | Current (shown) | Proposed | Own-page URL | Exact quote | Note |
|---|---|---|---|---|---|
| `andover/test-valley-borough-council-office` Test Valley Borough Council Office | (none) | keep removed (main showed 01264 368000) | https://andover.foodbank.org.uk/locations/ | - | 01264 368000 is Test Valley Borough Council's general switchboard. Not reverted: putting it back would break the no-general-council-switchboards rule (rule 5). Say if you want it back. |
| `ww-55475981` JNR8 Youth & Community Centre and Manley Park Methodist church | 0161 881 3744 | keep 0161 881 3744 (main had 0800 023 2692) | https://www.whalleyrange.org/contact-us/ | "T: (0161) 881 3744  Whalley Range Community Forum" (reads r1,r2,r3) | Not reverted: 0800 023 2692 is a Manchester City Council line (banned as a venue phone, rule 5). The source is the Whalley Range Community Forum page, not the venue's own site: confirm, or say to show no number. |
