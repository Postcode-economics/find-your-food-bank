"""Chichester District Foodbank, 26 Oct 2026.

The town collection centre (Unit 10, PO19 8ET) is open Monday 2–4pm, Wednesday 9.30–11.30am and Friday 4–6pm.
Two failures hid that:

* trussell_times kept only the last day of "Monday, Wednesday and Friday", so the card became Friday-only.
* the 3x-daily refresh confirmed a card when every stored clock time occurred somewhere on the page, so a
  Friday-only (or mashed) reading stayed "confirmed" while Monday and Wednesday were also listed.

Fixtures are shortened from the live pages fetched 26 Oct 2026 (locations page and the voucher page), plus the
day-list wording of those same sessions. The donation-warehouse block at the same postcode must not be used.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover, trussell_times as T
import classify as C
import hours_audit as A

# Real wording from https://chichesterdistrict.foodbank.org.uk/locations (text of the centre cards).
LOCATIONS = (
    "Our locations Chichester Collect your parcel: Unit 10, Chichester Trade Centre, Quarry Lane, Chichester, PO19 8ET "
    "Monday: 2-4pm Wednesday: 9.30-11.30am Friday: 4-6pm "
    "Selsey Collect your parcel: Selsey Methodist Church, High Street, Selsey, PO20 0QJ Friday: 10am - midday "
    "Midhurst Delivery only: Monday, Tuesday, Wednesday & Friday: 9.00am - 12.30pm "
    "To donate food You can donate directly to our Chichester warehouse: Unit 10, Chichester Trade Centre, Quarry Lane, "
    "Chichester, PO19 8ET Opening times Monday: 08:30-16:00 Tuesday: 09:00-12:00 Thursday: 08:30 – 15:30."
)
# Real voucher-card wording (one row per day) from /emergency-food/i-have-a-food-voucher.
VOUCHER = (
    "I have a food voucher 4 results See map Close Chichester Foodbank COLLECTION ONLY Part of Chichester District Foodbank "
    "01243 773687 Unit 10, Chichester Trade Centre Quarry Lane Chichester, West Sussex PO19 8ET Get directions Collection only "
    "Collection times Open today until 4:00 pm Monday 2:00 pm to 4:00 pm Tuesday Closed Wednesday 9:30 am to 11:30 am "
    "Thursday Closed Friday 4:00 pm to 6:00 pm Saturday-Sunday Closed "
    "Midhurst Centre Delivery Only Part of Chichester District Foodbank Midhurst, West Sussex GU29 9NF Delivery only "
    "Please note that this centre is not open to the public. Delivery times: Monday, Tuesday, Wednesday, Friday: 9am - 12.30pm. "
    "Selsey Centre: Collection Only Part of Chichester District Foodbank Selsey Methodist Church High Street Selsey PO20 0QJ "
    "Get directions Collection only Collection times Closed today Monday-Thursday Closed Friday 10:00 am to 12:00 pm Saturday-Sunday Closed "
    "See more information"
)
# The same Chichester sessions written as a day list. The old row pattern kept Friday only.
DAY_LIST = (
    "I have a food voucher 1 results See map Close Chichester Foodbank Part of Chichester District Foodbank "
    "01243 773687 Unit 10 PO19 8ET Get directions Collection times "
    "Monday, Wednesday and Friday 2:00 pm to 4:00 pm Tuesday Closed Thursday Closed Saturday-Sunday Closed Delivery times "
    "See more information"
)
DAY_LIST_AMP = DAY_LIST.replace("Monday, Wednesday and Friday", "Monday, Wednesday &amp; Friday")
TOWN = {"mon": [["14:00", "16:00"]], "wed": [["09:30", "11:30"]], "fri": [["16:00", "18:00"]]}
SELSEY = {"fri": [["10:00", "12:00"]]}

class Parser(unittest.TestCase):
    def test_locations_page_town_hours_ignore_warehouse_block(self):
        ot = discover.extract_times(LOCATIONS, "PO19 8ET")
        self.assertEqual(ot["status"], "TIMES_FOUND")
        self.assertEqual(ot["structured"], TOWN)
        self.assertNotIn("08:30", ot["raw"])
        self.assertEqual(discover.centre_role(LOCATIONS, "PO19 8ET"), "collection")

    def test_locations_page_selsey_not_given_the_next_centres_days(self):
        # The locations window runs on into Midhurst, which has no postcode, so this stays text rather than a guessed week.
        ot = discover.extract_times(LOCATIONS, "PO20 0QJ")
        self.assertTrue(ot is None or ot["status"] != "TIMES_FOUND" or ot["structured"] == SELSEY)

    def test_voucher_page_town_and_selsey(self):
        self.assertEqual(discover.extract_times(VOUCHER, "PO19 8ET")["structured"], TOWN)
        self.assertEqual(discover.extract_times(VOUCHER, "PO20 0QJ")["structured"], SELSEY)
        self.assertEqual(discover.centre_role(VOUCHER, "PO19 8ET"), "collection")
        self.assertEqual(discover.centre_role(VOUCHER, "GU29 9NF"), "delivery")

    def test_day_list_does_not_collapse_to_friday(self):
        for text in (DAY_LIST, DAY_LIST_AMP):
            cards = T.parse_cards(text)
            self.assertEqual(len(cards), 1, text)
            ot = T.to_ot(cards[0], "u", "2026-10-26")
            self.assertEqual(ot["structured"], {"mon": [["14:00", "16:00"]], "wed": [["14:00", "16:00"]], "fri": [["14:00", "16:00"]]})
            self.assertIn("mon", ot["structured"])
            self.assertNotEqual(list(ot["structured"]), ["fri"])

    def test_separate_sessions_stay_separate(self):
        text = ("X Hub Part of York Foodbank Road AB1 2CD Get directions Collection times "
                "Monday 2:00 pm to 4:00 pm and Wednesday 9:30 am to 11:30 am Delivery times")
        ot = T.to_ot(T.parse_cards(text)[0], "u", "d")
        self.assertEqual(ot["structured"], {"mon": [["14:00", "16:00"]], "wed": [["09:30", "11:30"]]})

class RefreshComparesDays(unittest.TestCase):
    FRI_ONLY = {"status": "TIMES_FOUND", "structured": {"fri": [["16:00", "18:00"]]}, "source_url": "https://x.org/locations"}

    def test_subset_of_days_is_not_confirmation(self):
        # Old check: Friday 4-6pm and the word Friday both occur on the page, so this was "confirmed".
        st, new, why = discover.confirm_times(self.FRI_ONLY, [LOCATIONS], "PO19 8ET",
                                              pages=[("https://x.org/locations", LOCATIONS)], source_url="https://x.org/locations")
        self.assertEqual(st, "changed", why)
        self.assertEqual(new["structured"], TOWN)
        self.assertTrue(new.get("collection"))

    def test_matching_table_is_confirmed(self):
        ot = {"status": "TIMES_FOUND", "structured": dict(TOWN), "source_url": "https://x.org/locations"}
        st, _, why = discover.confirm_times(ot, [LOCATIONS], "PO19 8ET",
                                            pages=[("https://x.org/locations", LOCATIONS)], source_url="https://x.org/locations")
        self.assertEqual(st, "confirmed", why)

    def test_source_page_wins_over_a_different_page(self):
        other = "Chichester PO19 8ET Friday: 4-6pm"
        st, new, why = discover.confirm_times(self.FRI_ONLY, [LOCATIONS, other], "PO19 8ET",
                                              pages=[("https://x.org/locations", LOCATIONS), ("https://x.org/", other)],
                                              source_url="https://x.org/locations")
        self.assertEqual(st, "changed", why)
        self.assertEqual(new["structured"], TOWN)

    def test_disagreeing_pages_are_flagged_not_overwritten(self):
        ot = {"status": "TIMES_FOUND", "structured": dict(TOWN)}
        pages = [("https://x.org/a", LOCATIONS), ("https://x.org/b", "Unit 10 PO19 8ET Friday: 10am - midday")]
        st, new, why = discover.confirm_times(ot, [t for _, t in pages], "PO19 8ET", pages=pages)
        self.assertEqual(st, "differs_review", why)
        self.assertIsNone(new)

    def test_delivery_only_is_flagged(self):
        ot = {"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "12:30"]]}}
        text = "Midhurst Centre Delivery Only Midhurst GU29 9NF Please note that this centre is not open to the public. Monday 9am - 12.30pm"
        st, new, _ = discover.confirm_times(ot, [text], "GU29 9NF")
        self.assertEqual(st, "differs_review")
        self.assertIsNone(new)

class CollectionPin(unittest.TestCase):
    def test_parent_with_collection_hours_stays_a_client_pin(self):
        import json, tempfile
        root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, "overrides"))
        for name in ("foodbank_manual.json", "foodbank_checks.json", "foodbank_extra_locations.json",
                     "foodbank_own_pages.json", "foodbank_address_fixes.json", "foodbank_added.json"):
            json.dump({}, open(os.path.join(root, "overrides", name), "w"))
        town = {"status": "TIMES_FOUND", "structured": dict(TOWN), "collection": True}
        items = [
            {"id": "chi", "type": "foodbank", "name": "Chichester District Foodbank", "foodbank": "Chichester District Foodbank",
             "address": "Unit 10, Quarry Lane", "postcode": "PO19 8ET", "lat": 50.83, "lng": -0.78, "network": "Trussell Trust", "opening_times": town},
            {"id": "chi/selsey", "type": "location", "name": "Selsey", "foodbank": "Chichester District Foodbank",
             "address": "Selsey Methodist Church", "postcode": "PO20 0QJ", "lat": 50.73, "lng": -0.79, "network": "Trussell Trust",
             "opening_times": {"status": "TIMES_FOUND", "structured": dict(SELSEY)}},
        ]
        C.classify(items, root)
        self.assertNotEqual(items[0].get("kind"), "warehouse")
        self.assertFalse(items[0].get("label_en"))
        hidden = json.loads(json.dumps(items))
        hidden[0]["opening_times"] = {"status": "TIMES_TEXT_ONLY", "raw": "Friday: 4-6pm"}
        C.classify(hidden, root)
        self.assertEqual(hidden[0].get("kind"), "warehouse")

class AuditDecision(unittest.TestCase):
    def test_town_warehouse_card_is_an_unambiguous_collection_fix(self):
        item = {"id": "chichester-district", "type": "foodbank", "kind": "warehouse", "name": "Chichester District Foodbank",
                "postcode": "PO19 8ET", "opening_times": {"status": "TIMES_TEXT_ONLY", "source_url": "https://chichesterdistrict.foodbank.org.uk/locations",
                "raw": "Friday: 4-6pm"}}
        row = A.judge_card(item, LOCATIONS)
        self.assertEqual(row["decision"], "apply")
        self.assertEqual(row["missing_days"], "mon|wed|fri")
        self.assertEqual(row["extra_days"], "")
        self.assertEqual(row["role"], "collection")
        self.assertNotIn("08:30", row["evidence"])

    def test_selsey_friday_matches_its_source(self):
        item = {"id": "chichester-district/selsey", "type": "location", "name": "Selsey", "postcode": "PO20 0QJ",
                "opening_times": {"status": "TIMES_FOUND", "structured": dict(SELSEY), "source_url": "https://chichesterdistrict.foodbank.org.uk/emergency-food/i-have-a-food-voucher"}}
        self.assertIsNone(A.judge_card(item, VOUCHER))

    def test_delivery_centre_is_not_applied(self):
        item = {"id": "chichester-district/midhurst", "type": "location", "name": "Midhurst", "postcode": "GU29 9NF",
                "opening_times": {"status": "TIMES_FOUND", "structured": {"mon": [["09:00", "12:30"]], "tue": [["09:00", "12:30"]], "wed": [["09:00", "12:30"]], "fri": [["09:00", "12:30"]]},
                                  "source_url": "https://chichesterdistrict.foodbank.org.uk/emergency-food/i-have-a-food-voucher"}}
        row = A.judge_card(item, VOUCHER)
        self.assertEqual(row["decision"], "review")
        self.assertIn("delivery", row["note"])

class NoCacheFallback(unittest.TestCase):
    """Rule 27: a times check reads the live page only. A saved copy is not a fallback."""
    def test_audit_ignores_saved_page_when_live_open_fails(self):
        import json, urllib.error
        url = "https://saved.example/locations"
        os.makedirs("/tmp/hours_audit_cache", exist_ok=True)
        json.dump({"http": 200, "text": "Monday 9am - 5pm Wednesday 9am - 5pm"}, open("/tmp/hours_audit_cache/poison.json", "w"))
        discover._cache[url] = {"http": 200, "final_url": url, "html": "<p>PO19 8ET Monday 9am - 5pm Wednesday 9am - 5pm</p>", "etag": "", "last_modified": "", "sha256": "saved"}
        def down(u):
            err = urllib.error.HTTPError(u, 403, "blocked", hdrs=None, fp=None)
            raise err
        rec = A.fetch_live(url, opener=down)
        self.assertEqual(rec["text"], "")
        self.assertNotIn("Monday", rec["text"])
        item = {"id": "saved-example", "type": "foodbank", "name": "Saved Example", "postcode": "PO19 8ET",
                "opening_times": {"status": "TIMES_FOUND", "structured": {"fri": [["10:00", "12:00"]]}, "source_url": url}}
        row = A.row_for(item, rec, False)
        self.assertEqual(row["decision"], "review")
        self.assertTrue(row["note"].startswith("unclear:"))
        self.assertEqual(row["source_hours"], "")
        self.assertIn("Opening times not listed. Call before you go.", row["note"])
        discover._cache.pop(url, None)

    def test_mismatch_check_ignores_saved_page_when_live_open_fails(self):
        import urllib.error
        url = "https://x.org/"
        html = "<html><body><p>Riverside Food Bank AB1 2CD Monday 9am - 11am Wednesday 2pm - 4pm.</p>" + (" lorem" * 40) + "</body></html>"
        discover._cache[url] = {"http": 200, "final_url": url, "html": html, "etag": "saved", "last_modified": "", "sha256": "saved"}
        item = {"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": url,
                "opening_times": {"status": "TIMES_FOUND", "structured": {"fri": [["10:00", "12:00"]]}}}
        def down(*a, **k):
            raise urllib.error.URLError("live down")
        with unittest.mock.patch("urllib.request.urlopen", side_effect=down):
            log = discover.cross_check_times([item], "fb", "opening_times", fetcher=discover.fetch_live, threads=1)
        self.assertNotEqual(log["a"]["status"], "changed")
        self.assertEqual(item["opening_times"]["structured"], {"fri": [["10:00", "12:00"]]})
        self.assertNotIn("mon", item["opening_times"]["structured"])
        discover._cache.pop(url, None)

    def test_shards_cover_every_listing_once(self):
        items = list(range(10))
        parts = [A.shard_of(items, i, 4) for i in range(4)]
        self.assertEqual(sorted(x for p in parts for x in p), items)
        self.assertLessEqual(max(len(p) for p in parts) - min(len(p) for p in parts), 2)

    def test_daily_sweep_drops_saved_hours_when_live_page_fails(self):
        import full_check
        r = {"ok": False, "hours_hash": "abc", "hours_sample": ["monday 9-5"], "seasonal": "closed over christmas"}
        full_check.drop_saved_hours(r)
        self.assertEqual(r["hours_hash"], "")
        self.assertEqual(r["hours_sample"], [])
        self.assertIsNone(r["seasonal"])
        src = open(os.path.join(os.path.dirname(__file__), "..", "scripts", "full_check.py"), encoding="utf-8").read()
        fail = src.split("if not r['ok']:")[1].split("stats['ok']")[0]
        copied = fail.split("drop_saved_hours")[0]
        self.assertNotIn("hours_hash", copied)
        self.assertIn("drop_saved_hours", fail)
        self.assertIn("hours_status", fail)

if __name__ == "__main__":
    unittest.main()
