## What the system learned (signals)

- Source trust (phone agrees with own site, minus hand corrections): IFAN 0.37 (21 checked), other 0.82 (9 checked), Give Food 0.90 (692 checked)
- Places with change signals (dead link, closure wording, Facebook, bounce): 81
- Checks moved up for next run: 1054 sites (corrections 134, signals 128, season 0, demand 0, visitor reports 0)
- Seasonal timing: boost 0.00 this week (1 weeks of history (2026))
- Demand: no visitor data yet (reports/demand.json not present) - no effect; visitor reports: no visitor reports recorded yet - no effect
- Hardest hosts to reach: bsfoodhub.org.uk (100% of 1 sites failing), caistorfoodbank.org (100% of 1 sites failing), churchesfoodbank.org.uk (100% of 1 sites failing)
- Weekly self-review: correction not enough data, signal not enough data
- Weekly accuracy trend: 2026-W43 reachable 95%, phones agree 93%, corrections 93
- New places found are never added automatically: they wait in reports/pending_dean.md for your OK.

### Weights now (bounded 50%-150% of default, max 10% change a week)

- correction: 0.500
- demand: 0.300
- season: 0.300
- signal: 0.800
- trust: 0.400
- visitor: 0.800

### Top 20 boosted sites

- https://www.humansmcr.org: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.nbil-community.org: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.waiyin.org.uk: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://stpaulsparkside.org.uk/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.caritassalford.org.uk/service/cornerstone-centre/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.holytrinitywesterhailes.org.uk: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.gospelcentre.co.uk/get-involved.html: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.ibijokefoundation.co.uk/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.cfydc.org.uk/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.252}
- https://www.axminsterwellbeing.com: {'correction': 0.5, 'signal': 0.6, 'trust': 0.252}
- https://cartertonfoodbank.co.uk: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://ccg.scot/projects/1073/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/BancBwydLlandysul/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/kirriefoodhub/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/WAMCCommunity: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/Drighlingtonfoodbank: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/birchgrovecommunityfoodbank/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://dwellingplaceglasgow.org/storehouse/: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.minerslamp.org: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}
- https://www.facebook.com/profile.php?id=100086170811325: {'correction': 0.5, 'signal': 0.8, 'trust': 0.039}

