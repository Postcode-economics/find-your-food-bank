"""31 Oct 2026: national web sweep batch 2 – hand-verified shelters and day centres (phone verbatim on own/council page).
Hermetic: no network."""
import json, os, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
OV = os.path.join(ROOT, "overrides")
NEW_IDS = [
    "man-cathedral-archer-project",
    "man-doorstep-hull",
    "man-positive-pathways-drop-in-depaul",
    "man-dominion-community-hub",
    "man-bradford-day-shelter-salvation-army-the-orchard",
    
    "man-crisis-skylight-newcastle",
    "man-first-stop-darlington",
    "man-700-club-hostel",
    
    "man-shiloh-rotherham",
    "man-harbour-place",
    
    "man-angel-trust-safe-night-hub",
    
    "man-catching-lives-canterbury-open-centre",
    "man-portsmouth-rough-sleeping-hub-society-of-st-james-",
    "man-trinity-winchester",
    
    "man-folkestone-rainbow-centre-homeless-support-service",
    "man-dover-outreach-centre",
    "man-gravesham-sanctuary-day-centre-winter-night-shelte",
    
    "man-stonepillow-chichester-hub",
    "man-stonepillow-bognor-regis-hub",
    "man-bognor-housing-trust",
    "man-antifreeze-off-the-fence",
    
    "man-wycombe-homeless-connection-support-centre",
    "man-the-hope-hub",
    "man-o-hanlon-house-homeless-oxfordshire",
    "man-the-foxton-centre-homeless-day-centre",
    "man-the-wellspring",
    "man-urban-outreach-street-life-drop-in-amber-centre",
    "man-cornerstone-day-centre-caritas",
    "man-salford-loaves-fishes-drop-in",
    "man-crisis-skylight-merseyside",
    "man-the-brick-queen-s-hall-action-on-poverty-day-centr",
    "man-petrus-hub",
    "man-cath-harold-tomlins-centre",
    "man-salvation-army-bridge-project-blackpool-citadel",
    "man-streetlife-the-base-young-people-16-25",
    "man-furness-homeless-support-group",
    "man-chorley-help-the-homeless-community-cafe",
    "man-routes-to-roots-genesis-centre",
    "man-lantern-trust",
    "man-st-petrocs-truro-resource-centre",
    "man-st-petrocs-breadline-centre",
    "man-leonard-stocks-centre",
    "man-alongside-manvers-street-hostel",
    "man-the-freedom-centre",
    "man-alabare-unity-house-drop-in",
    "man-somewhere-to-go-project",
    "man-p3-stroud-community-based-support-drop-in",
    "man-ymca-bournemouth-delta-house-hostel",
    "man-bh1-project-salvation-army-boscombe",
    
    "man-the-hope-centre-minehead",
    "man-hosford-homeless-hostel-east-belfast-mission",
    
    "man-shekinah-centre",
    "man-turnaround-centre-formerly-bristol-methodist-centr",
    "man-cirdic-churches-in-reading-drop-in-centre",
    
    "man-maidstone-day-centre",
    "man-spires-centre",
    "man-the-margins-project-union-chapel",
    "man-new-horizon-youth-centre",
    "man-greenwich-homeless-project-day-centre",
    "man-crisis-skylight-brent",
    "man-crisis-skylight-croydon",
    "man-merton-faith-in-action-homeless-drop-in",
    "man-barons-court-project",
    
    "man-providence-row-dellow-centre",
    "man-sutton-night-watch-day-centre",
    "man-salvation-army-the-well-croydon",
    "man-salvation-army-founders-house-hopetown-lifehouse",
    "man-ymca-romford",
    "man-bethany-welcome-centre",
    "man-aberdeen-cyrenians-direct-access",
    
    "man-thrashbush-quadrant-temporary-accommodation",
    "man-manse-avenue-temporary-accommodation",
    "man-tarbolton-road-temporary-accommodation",
    "man-greenlaw-house",
    "man-sir-julian-hodge-hostel-the-wallich",
    "man-brynmenyn-house-the-wallich",
    "man-ty-ogwr-hostel-the-wallich",
    "man-bridgend-solutions-centre-the-wallich",
    "man-dinas-fechan-hostel-the-wallich",
    "man-ty-tom-jones-the-wallich",
    "man-ty-raena-the-wallich",
    "man-corporation-street-the-wallich",
    "man-ynys-mon-supported-accommodation-the-wallich",
    "man-st-john-s-hostel-the-wallich-b-item-resolved",
    "man-paxton-street-hostel-goleudy",
    "man-maple-tree-house-goleudy",
    "man-padley-ymca-derbyshire-community-hub",
    "man-wintercomfort-for-the-homeless",
    
    
    "man-pottergate-arc-salvation-army",
    "man-harp-bradbury-day-centre",
    
    "man-the-falcon-centre-falcon-support-services",
    "man-beacon-house",
    "man-the-chapman-centre-ihag",
    "man-the-garden-house-light-project-peterborough",
    "man-doorway-young-people-16-25",
    "man-house-of-bread-cafe-43",
    "man-bishopbridge-house-st-martins",
    
    "man-trafalgar-house-sanctuary",
    
    "man-the-bridge-homelessness-to-hope",
    "man-hope4-rugby",
    "man-hope-community-services",
    "man-the-ferry-project",
    "man-lee-s-place-community-power",
    "man-gloucester-city-mission-homeless-day-provision",
    "man-salvation-army-booth-house-swindon",
    "man-crisis-skylight-south-wales",
    "man-999-club-the-gateway",
    
    "man-the-upper-room-ur4meals",
    "man-action-for-barnsley-homeless",
    "man-harrogate-homeless-project-springboard-day-centre",
    "man-shoc-slough-homeless-our-concern",
    "man-york-road-project",
    "man-renewed-hope-drop-in-day-centre",
    "man-st-joseph-s-night-shelter-stonepillow",
    "man-leatherhead-start",
    "man-hug-safe-space-bexhill-rother-homelessness-unity-g",
    "man-genesis-trust-lifeline",
    "man-the-zone-plymouth-youth-housing-homelessness-drop-",
    "man-highway-house",
    "man-simon-community-scotland-edinburgh-support-hub",
    "man-simon-community-scotland-glasgow-access-hub",
    "man-airth-court-temporary-accommodation",
    "man-ymca-cardiff-the-walk",
    "man-cornerstone-house-the-wallich",
    "man-northampton-hope-centre-hand-up-homeless-centre",
    "man-pathways-of-chesterfield",
    "man-centrepoint-outreach-drop-in",
    "man-first-stop-centre",
    
    "man-salvation-army-newcastle-under-lyme-homeless-hub",
    "man-the-haven-day-centre-swindon-night-shelter",
    "man-the-forge-project",
    "man-turning-tides-st-clare-s-community-hub",
    "man-alabare-place-drop-in",
    "man-taunton-open-door",
    "man-launchpad-reading-drop-in-the-stables",
    "man-open-door-homeless-hub-hightown",
    "man-streets2homes-day-centre",
    
    "man-birmingham-city-mission-care-centre",
    "man-crisis-skylight-birmingham",
    "man-st-wilfrid-s-centre",
    "man-hope-trinity",
    "man-goleudy-access-point",
    "man-p3-wolves-hub-navigator",
    
    "man-crisis-skylight-oxford",
    "man-carecent",
    "man-crisis-skylight-edinburgh",
    "man-bradford-no-second-night-out-humankind-discovery-h",
    "man-coventry-cyrenians",
    "man-joining-communities-together-jct",
    "man-the-macari-centre-victoria",
    "man-home4good-centre-dunfermline",
    "man-victoria-house",
    "man-crossreach-cunningham-house",
    
    "man-chess-homeless",
    
    "man-oak-house-homeless-action"
]


def _j(f):
    return json.load(open(os.path.join(OV, f), encoding="utf-8"))


class Batch2(unittest.TestCase):
    def test_overrides(self):
        man = {x["id"]: x for x in _j("shelters_manual.json")}
        ver, app, base = _j("shelters_verified.json"), _j("approved_new_places.json")["shelters"], _j("phone_baseline.json")["listings"]
        for i in NEW_IDS:
            m = man[i]
            self.assertTrue(m["phone"] and m["postcode"] and m["lat"] and m["lng"], i)
            self.assertEqual(ver[i]["phone"], m["phone"], i)
            self.assertTrue(ver[i]["evidence_url"].startswith("http"), i)
            self.assertIn(i, app)
            self.assertEqual(base[i]["phone"], m["phone"], i)
            if isinstance(m["facilities"], list):
                self.assertTrue(m["facilities"] and m.get("facilities_quote"), i)
            else:
                self.assertEqual(m["facilities"], "Not stated", i)
            if m["groups"] and i != "man-new-horizon-youth-centre":
                self.assertTrue(m.get("groups_quote"), i)
            self.assertEqual(m["who_for"], m["groups"] or "Not stated", i)
            self.assertNotIn("Women only", m["groups"], i)
            if "wheelchair" in m:
                self.assertIn(m["wheelchair"], ("yes", "partial", "no", "Not stated"), i)
                if m["wheelchair"] != "Not stated":
                    self.assertTrue(m.get("wheelchair_quote"), i)


if __name__ == "__main__":
    unittest.main()


class OptionAGate(unittest.TestCase):
    """Dean 1 Nov 2026 option A: an unread who-for is published as 'Not stated', not held as a gap."""
    def test_not_stated_passes_gate(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        import publish_gate as pg
        base = {"id": "x", "tel": "1", "phone": "01234 567890"}
        self.assertEqual(pg.problems("shelters", dict(base, groups=[], who_for="Not stated")), [])
        self.assertEqual(pg.problems("shelters", dict(base, groups=[])), ["no sourced 'who it's for'"])
