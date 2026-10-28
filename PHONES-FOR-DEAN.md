# Phones for Dean: shelters audit 27 Oct 2026 (PR #233)

None of these are applied. The site still shows the current number. A phone is applied automatically only when it's on the organisation's own site, identical on 2 reads, with no conflicting own page (Dean, 28 Oct 07:02). Each number below fails that test.

| Shelter (id) | Current | Proposed | URL | Exact quote | Status |
|---|---|---|---|---|---|
| DENS The Elms, Hemel Hempstead (`hl-dens-the-elms`) | 01442 800131 | 01442 262274 | https://www.newhope.org.uk/mta-ea-page-1 | "The Elms Redbourn Road Hemel Hempstead HP2 7AZ 01442 262 274 receptiontheelms@dens.org.uk" | **Held: third-party source only.** DENS's own page (https://www.dens.org.uk/our-services/outreach-accommodation/) does not show 01442 262274. It gives 01442 800131 for street outreach. |
| Talbot Kingston Halls, Glasgow (`osm-way-556071354`) | 0141 429 4541 | 0141 418 1955 | https://talbotassociation.org/our-services-1 | "Kingston Halls Direct Access Hostel Tel: 0141-418-1955" | **Held: conflicting own page.** The quote was identical on 2 reads on 28 Oct, but two other Talbot pages give the current number at the same Kingston Halls address. https://talbotassociation.org/get-in-touch-1 says "Talbot Association Kingston Halls Glasgow G5 8RE 01414294541", and https://talbotassociation.org/privacy-policy says "Talbot Association Kingston Halls Glasgow G5 8RE Telephone: 0141 429 4541". |

## Not proposed

- **Oak Tree House, Lancaster (`osm-way-1119807447`):** 0300 111 1212 is kept. The only new contact (email gatewaylancaster@calico.org.uk, operator Acorn Recovery Projects) comes from the Lancashire Service Finder directory, not the operator's own site, so it isn't used.
- **James House, York (`osm-way-169564851`):** 01904 554500 is York's Housing Options main line and is flagged. No own-page number for the hostel was found, so there's nothing to propose.
- **Peasholme, York (`osm-node-1533578890`):** its phone is handled in #238 (Dean approved 01904 551901). This PR doesn't touch Peasholme's phone.
