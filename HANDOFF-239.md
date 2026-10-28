# HANDOFF #239 (06:2x GMT 28 Oct)
Status of the items below on batch-listings:
- APPLIED: all 14 Bot 4 Trussell phones EXCEPT 2 skipped on purpose (on Dean's list): newham-district/bonny-downs (page postcode E6 6DQ != our E6 6BT), waveney/framlingham-delivery-team (card has no address, can't postcode-match). Royal Docks 020 7476 1666 + 'Food bank help line' label applied.
- APPLIED: Motion closures 4 (Newham 5 times/numbers, newhamfoodbank.org.uk links, East Ayrshire link + note); Bot 3 pass 3 (2 links, 3 email labels, Maghull/Ilminster on list); Luton Marsh Farm removed (exclude + test + undo); 8 not-on-list labels; MK help line note; Merthyr on list.
- APPLIED (commit 4ff63ccd6): 06:20 times recheck, 5 fixes re-fetched twice + postcode matched; Croydon appointment-only notice; Wendover HELD on Dean's list. Tests in tests/test_listings_batch_28oct.py (12 pass).
- LEFT: full test suite + iPhone WebKit backup off/on NOT run (stopped by instruction). origin/main fda5abbc6 already merged; re-check for newer main.

---
# Listings #239 items sent 05:52-06:01 GMT 28 Oct (the worker was stopped, so check each against the branch; apply any that are missing)
Rules: own page only, re-fetch and match by postcode, log every change with an undo, never invent anything.
## Bot 4 Trussell phone fixes (14). Table at the end of /workspace/review/phones-bot4-trussell-recheck.md
portsmouth/city-life-church 02392 987976 -> 02392 660844; hastings/downs-farm-community-centre 01424 753322 -> 01424 755990;
clevedon-district/yatton 07722 769529 -> 07351 898114 (https://clevedondistrict.foodbank.org.uk/locations/);
newham royal-docks 020 7511 1232 -> 0207 476 1666 labelled 'Food bank help line' (name unchanged; the 'St John's Community Centre' possible renaming goes on Dean's list);
newham bonny downs -> 0208 586 7070; bridgend pencoed -> 07704 763509; caerphilly van cc -> 07923 164907; taff bargoed treharris -> 01443 706845;
aylesbury southcourt baptist -> 07768 566089 (by arrangement only); aylesbury tabitha -> 07429 924842; aylesbury methodist -> 07762 876544;
fosse wellesbourne -> 07581 297187 (collection by appointment only); waveney framlingham -> 07388 791126; b30 cotteridge quaker -> 07582 143972.
## Motion closures 4 (/workspace/review/motion-closures-4.md)
Newham, from newhamfoodbank.org.uk/get-help (2nd read must match): Manor Park E12 6RH Tue 10-12 020 8470 9930; London Ghana SDA E13 8NF Thu 18-20 0207 474 8095; Rehoboth E13 8QB Sat 9-11 07951 612405; Royal Docks E16 2JB Mon-Fri 10:30-14:30; WGMI E13 9LB Sun 11-13 07944 101267. Replace the newham.foodbank.org.uk link.
East Ayrshire link -> https://www.cvoea.co.uk/what-we-do/ayrshire-east-foodbank/, plus the appointment note (01563 574000 opt 3, Mon/Tue/Thu/Fri 9-4:30, Belford Mill KA1 3HZ).
## Bot 3 pass 3
wellingborough-district link -> https://daylightcf.org/foodbank ; foodshed link -> https://stevenage-vineyard.co.uk/compassion/foodshed/ ; St Ives (Cambs), the-hive, storehouse-melton get the label 'Contact by email (no public phone)'. Maghull and Ilminster go on Dean's list (no change).
## Closures / labels
REMOVE luton/marsh-farm if https://lutonfoodbank.org.uk/get-food/ still says CLOSED (Dean's own-source rule).
Label 'Not on the food bank's current list, call before you go' + Dean's list: Horsham Lavinia House, St Mary's Church, Hub on the Move Beech Road, Hub on the Move Warnham; Andover The Castle Practice; St Albans Wheathampstead; Gloucester Kingsholm; Carmarthen The Table.
Milton Keynes: add 0300 303 4933 'Food bank help line' if MK's own site shows it. Merthyr Cornerstone/CVC Cwmbach -> Dean's list.

## 06:20 Claude Trussell times recheck (own page, 2 identical reads 06:05/06:10Z, logged with undo, add to Dean's review list)
- The Net Walderslade ME5 0QX: Thu 09:30–12:00 only (remove the office-phone lines from times)
- Twydall ME8 6LQ: Tue 12:30–14:30, Fri 10:30–12:30
- Croydon Thornton Heath Hub CR7 8SA: Thu 11:00–13:00, appointment only
- Mill End WD3 7HJ: Tue 13:45–16:00, Fri 10:00–12:00
- St Lawrence Abbots Langley WD5 0AS: Tue 10:00–13:00, Thu 09:00–11:00, Fri 10:00–13:00 (A/L Citizens Advice card at same postcode keeps its hours)
- HOLD (not applied): Wendover HP22 6JG delivery block shows all closed; known->closed is forbidden. Keep the current delivery-only note.
Source: /cursor/stores/store-a2897e7d-0772-49bb-b9b2-9822a28b017b/grok-bot/agents/6ee7dc77-b54e-4856-8e8c-8da95547d0df/assets/01M60JMXSFASNH246CGJJQB72K.md
