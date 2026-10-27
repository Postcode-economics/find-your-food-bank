# Emergency shelter preview — research backup

Updated: 2026-10-25 (Europe/London), the same day the preview rules and tests were added.

Status: preview only. The live site does not show it unless the address has `?preview=emergency`. Approved by Dean 27 Oct 2026 as a hidden preview.

## What the preview does

- It covers any emergency (floods, storms, wildfires, landslides, coastal erosion, earthquakes, chemical, industrial or gas incidents, major fires, building collapse, long power or water outages, and any council or police evacuation). It is not only weather.
- The badge reads **Emergency shelter**. **Severe weather: open tonight** is only for SWEP, and only while the council page says SWEP is active.
- Data comes from the feeds already in `scripts/weather.py` (Met Office, Environment Agency, SEPA, Natural Resources Wales, UK Emergency Alerts), extended rather than replaced.
- Every item has an open-until time. If the source states one, that time is used. Otherwise it is the end of the related warning plus 6 hours, and never more than 24 hours after the item was added.
- A cached page hides a card in the browser once that time has passed.
- If a feed has not been fetched for over 30 minutes, the banner says the warning info may be out of date. After 2 hours the banner is hidden and only the source links stay.
- Cards show 999 and, in England, Scotland and Wales, Floodline 0345 988 1188. In Northern Ireland they show 0300 2000 100.
- Access, pets and beds are shown only when the source states them.
- A council rest centre can be listed at once in a fast-moving disaster, and Dean is told afterwards. Anything that is not from a council or other official announcement is held until Dean says yes.
- Utility, police and fire pages, and the BGS earthquake feed, are triggers only. They re-check the council. They do not create a shelter card on their own, and an earthquake does not raise the banner unless there is an official alert.
- There is a text-only list at `emergency.txt` (999 and Floodline on top, no JavaScript).
- The map key's fourth entry is shown only when a shelter marker is live.
- Colour, signed off 25 Oct 2026: every red is `#FF3B30` (2px outline, 6px left edge, badge fill, 999 button, map pin). Text on red is `#FFFFFF`, weight 900. The badge is 16px. The font stack is system-ui, -apple-system, "Segoe UI", Roboto, sans-serif. The pin is the UN OCHA House icon (CC0) in white on the red pin, with a white edge.
- The repeating 10-minute check, the email sign-ups, and sending the watchdog message are not switched on. The rules are in `scripts/weather.py` and covered by tests. A manual workflow (`.github/workflows/emergency-preview.yml`) can write the preview report. It has no schedule.

## Sources not used, because they could not be verified

These are the ones the 25 Oct plan could not verify. They are not used as shelter sources:

- Natural Resources Wales API content (the endpoint exists; the body needs a key, so the content was not checked)
- Ready Scotland, https://www.ready.scot/ and the flooding page (HTTP 202)
- Cardiff council emergency page (HTTP 403)
- Edinburgh, Lincoln and Croydon council emergency pages (guessed URLs returned HTTP 404)
- Armagh, Banbridge and Craigavon emergency subpage (not found; the council home page itself was reachable)
- UK Power Networks power-cut map (HTTP 403)
- 105 power cut line, https://www.powercut105.com/ (HTTP 403)
- Southern Water incidents (HTTP 403)
- Sussex Police home page (HTTP 403)
- ISO 7010 (iso.org returned HTTP 403, so an emergency-shelter sign could not be confirmed)
- No verified wildfire, landslide or coastal-erosion feed
- No standard UK rest-centre pictogram on the Cabinet Office emergency response and recovery page
- No common council icon for a rest centre
- No national rest-centre feed

The map pin uses UN OCHA Humanitarian Icons `House.svg`, CC0 1.0, from https://github.com/UN-OCHA/humanitarian-icons (saved as `assets/ocha-house-white.svg`).

Floodline 0345 988 1188 and the Northern Ireland flooding line 0300 2000 100 are the numbers the plan checked on GOV.UK and NI Direct. They are national lines, not a claim that a particular shelter is open.
