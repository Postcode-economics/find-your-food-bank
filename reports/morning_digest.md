# Morning digest - 2026-10-25

## Alerts this run

- **Food bank closed**: Removed because its own site says it closed: Welshpool and District Foodbank
- **Amber/red weather or severe flood warning**: Amber warning of wind affecting Dumfries, Galloway, Lothian & Borders (shelters/warm spaces: Edinburgh City Salvation Army, Fa’side Community Kitchen, Granton Skills & Wellbeing Centre, Kirkliston Parish Church, Pencaitland Lunch Club, The Heart; SWEP: none); Amber warning of wind affecting Grampian (shelters/warm spaces: Alford Fly Cup at St. Andrew’s, Peterhead Baptist Church; SWEP: none); Amber warning of wind affecting Highlands & Eilean Siar (shelters/warm spaces: none matched; SWEP: none); Amber warning of wind affecting North East England (shelters/warm spaces: Coxhoe and Area Community Pantry and Foodbank; SWEP: none); Amber warning of wind affecting North West England (shelters/warm spaces: Bamford Chapel & Norden URC, Cafe Oasis, Christ Church Coffee Lounge, Cornerstone United Reformed Church @ Parrs Wood Road, Currock House Community Centre, Fairhaven Methodist Church, Gateway, Greenmount Old School, Hope URC Denton, Leyland United Reformed Church; SWEP: none); Amber warning of wind affecting Central, Tayside & Fife (shelters/warm spaces: Community Warm Space, St. Mary's, Broughty Ferry, Wardlaw Museum, wee blether with soup and sandwich at Seescape; SWEP: none); Amber warning of wind affecting Yorkshire & Humber (shelters/warm spaces: Glusburn Community & Arts Centre, Munch and Mingle, Norton Hive Community Library and Hub, Sherburn and Villages Community Library & Information Hub, St Luke’s Church, St. Thomas Church, Sutton-in-Craven, YMCA Scarborough; SWEP: none); Amber warning of wind affecting Strathclyde (shelters/warm spaces: Glasgow City Mission Overnight Welcome Centre, Talbot Association; SWEP: none) - see reports/weather.md

## Everything else

- Changes since last run: 52 (0 new, 1 removed, 51 field updates)
- Likely duplicates on the map: 23 (reports/duplicates.md)
- Weather/flood warnings: 85 (reports/weather.md)
- Source quality scores: reports/source_scores.md
- Source errors this run: 43 (reports/source_errors.json)
- SWEP councils still to check: 25 (reports/swep_tracker.md)
- Daily review list: reports/daily_review.md

## What the system learned

- Checks recorded so far: 3856 across 2549 sources/places
- Top movers up: https://www.sheffield.gov.uk/node/6758/stannington-food-bank (+0.08), https://www.achurchnearyou.com/church/17619/service-and-events/events/900428/ (+0.08), https://therivermanchester.org.uk/ (+0.08), https://telfordcrisissupport.org.uk/ (+0.08), https://stmonica.co.uk/social-action (+0.08)
- Top movers down: http://breadlineproject.org (-0.17), http://portlandfoodbank.co.uk (-0.17), http://www.foodbank4whitby.org.uk (-0.17), http://www.sidvalleyfoodbank.org.uk (-0.17), https://3food4u.org (-0.17)
- Sources/places with useful finds today: https://www.cambridgeshire.gov.uk/news/cold-weather-health-alert-advice-for-staying-warm-and-well-1, https://stmonica.co.uk/social-action, https://telfordcrisissupport.org.uk/, https://therivermanchester.org.uk/, https://www.achurchnearyou.com/church/17619/service-and-events/events/900428/
- Backing off (repeated failures, retried within 7 days): https://www.hertfordshire.gov.uk/about-the-council/news/press-releases/come-in-from-the-cold-to-one-of-hertfordshire&#39;s-warm-spaces.aspx (11 fails), https://www.hertfordshire.gov.uk/microsites/herts-careline/about/news/new-&#39;warm-spaces&#39;-directory-launched-in-hertfordshire.aspx (11 fails), http://bsfoodhub.org.uk (2 fails), http://www.caistorfoodbank.org (2 fails), http://www.churchesfoodbank.org.uk (2 fails)

## What the system learned (signals)

- Source trust (phone agrees with own site, minus hand corrections): IFAN 0.38 (22 checked), other 0.82 (9 checked), Give Food 0.90 (696 checked)
- Places with change signals (dead link, closure wording, Facebook, bounce): 78
- Checks moved up for next run: 1054 sites (corrections 134, signals 124, season 0, demand 0, visitor reports 0)
- Seasonal timing: boost 0.00 this week (1 weeks of history (2026))
- Demand: no visitor data yet (reports/demand.json not present) - no effect; visitor reports: no visitor reports recorded yet - no effect
- Hardest hosts to reach: alhudauk.com (100% of 1 sites failing), assyntdevelopmenttrust.org (100% of 1 sites failing), betheltrustpt.co.uk (100% of 1 sites failing)
- Weekly self-review: correction did not pay off (-10%), signal paid off (+10%)
- Weekly accuracy trend: 2026-W43 reachable 96%, phones agree 93%, corrections 93
- New places found are never added automatically: they wait in reports/pending_dean.md for your OK.
