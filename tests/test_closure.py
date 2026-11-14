import sys, os, unittest, datetime, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import closure as C
T = datetime.date(2026, 10, 21)
KT = "Kentish Town Foodbank (Distribution Centre- Clients only) CLOSED 27TH AUGUST 2026 | Thurs 10.30am – 1pm | Kentish Town Congregational Church, Kentish Town Rd, Church Avenue, NW1 8PD | Kentish Town Foodbank (warehouse) | Thurs 11.30-1.30 | C/O Revelation Church | 39-41 Buswell Rd NW5 2AB"
class T1(unittest.TestCase):
    def test_kentish_town_closed(self): self.assertTrue(C.detect(KT, "NW1 8PD", T))
    def test_neighbour_block_not_closed(self): self.assertIsNone(C.detect(KT, "NW5 2AB", T))
    def test_future_date_not_closed(self): self.assertIsNone(C.detect("St Mary's Hall, AB1 2CD. Closed 5th December 2026", "AB1 2CD", T))
    def test_routine_closed_ignored(self): self.assertIsNone(C.detect("Opening times Mon Closed Tue 10:00 - 12:00 Wed Closed. Hall, AB1 2CD. Closed on bank holidays", "AB1 2CD", T))
    def test_temporary_ignored(self): self.assertIsNone(C.detect("Hall, AB1 2CD is temporarily closed for refurbishment", "AB1 2CD", T))
    def test_permanently_closed(self): self.assertTrue(C.detect("Our Elm Road centre, AB1 2CD, has now closed. Please use Oak Street.", "AB1 2CD", T))
    def test_no_longer_operating(self): self.assertTrue(C.detect("Church Hall, AB1 2CD - this centre is no longer operating", "AB1 2CD", T))
    def test_postcode_absent(self): self.assertIsNone(C.detect("This centre has closed", "AB1 2CD", T))
    def test_apply_removes_and_logs(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/overrides"); os.makedirs(d + "/logs")
        json.dump({"a": {"url": "u", "evidence": "closed"}}, open(d + "/overrides/foodbank_closed.json", "w"))
        json.dump({"recently_closed": [{"id": "old", "name": "Old", "closed_on": "2026-08-01"}, {"id": "mid", "name": "Mid", "closed_on": "2026-10-01"}]}, open(d + "/logs/foodbank_closed.json", "w"))
        items = [{"id": "a", "name": "A", "postcode": "AB1 2CD", "website": ""}, {"id": "b", "name": "B", "postcode": "AB1 2CE", "website": ""}]
        gone = C.apply(items, d, T, fetcher=lambda u: (u, ""))
        self.assertEqual(gone, ["a"]); self.assertEqual([i["id"] for i in items], ["b"])
        log = json.load(open(d + "/logs/foodbank_closed.json")); ids = [r["id"] for r in log["recently_closed"]]
        self.assertIn("a", ids); self.assertIn("mid", ids); self.assertNotIn("old", ids)  # 30-day window
    def test_unreachable_changes_nothing(self):
        items = [{"id": "x", "name": "X", "postcode": "AB1 2CD", "website": "https://example.invalid/"}]
        self.assertEqual(C.check_all(items, fetcher=lambda u: (u, ""), today=T), {})
    def test_site_fetch_detects(self):
        items = [{"id": "kt", "name": "KT", "postcode": "NW1 8PD", "website": "https://kt.example/"}, {"id": "wh", "name": "WH", "postcode": "NW5 2AB", "website": "https://kt.example/"}]
        self.assertEqual(set(C.check_all(items, fetcher=lambda u: (u, "<p>" + KT + "</p>"), today=T)), {"kt"})
class T2(unittest.TestCase):
    SH = "Shoreham Foodbank (Shoreham Baptist Church) Opening times Mon Closed Tue 10:00 - 12:00 Address Shoreham Baptist Church, Western Rd Shoreham-by-Sea BN43 5WD Directions via Google Maps Oasis Foodbank - This is now closed Opening times Mon Closed Address Oasis Christian Fellowship, Hangleton Way, Hove BN3 8EQ Directions via Google Maps"
    def test_next_block_closure_not_leaked(self): self.assertIsNone(C.detect(self.SH, "BN43 5WD", T))
    def test_own_block_closure(self): self.assertTrue(C.detect(self.SH, "BN3 8EQ", T))
    def test_exceptional_one_day_ignored(self): self.assertIsNone(C.detect("Our Southall Centre at Southall Dominion chapel UB1 1AA is exceptionally CLOSED on 18 APRIL 2026", "UB1 1AA", T))
    def test_holiday_range_ignored(self): self.assertIsNone(C.detect("Hall, BS23 1AA. Closed between 25th December and 1st January 2026", "BS23 1AA", T))
class T3(unittest.TestCase):
    def test_hold_keeps_pin(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/overrides"); os.makedirs(d + "/logs")
        json.dump({"_hold_for_review": ["kt"]}, open(d + "/overrides/foodbank_closed.json", "w"))
        items = [{"id": "kt", "name": "KT", "postcode": "NW1 8PD", "website": "https://kt.example/"}]
        self.assertEqual(C.apply(items, d, T, fetcher=lambda u: (u, KT)), []); self.assertEqual(len(items), 1)
        self.assertEqual(json.load(open(d + "/logs/foodbank_closed.json"))["held_for_review"][0]["id"], "kt")
class T4(unittest.TestCase):
    # Exact-value lock only: the gallery-closure wording is ignored for this id,
    # but a different venue-level closed reading still counts.
    GALLERY = "Please note, The Vivarium and Nature’s Library are now closed until May 2027, while we work on something very exciting."
    PHRASE = "The Vivarium and Nature’s Library are now closed until May 2027"
    VENUE = "Manchester Museum, M13 9PL, is now closed."
    def _root(self, phrase):
        d = tempfile.mkdtemp(); os.makedirs(d + "/overrides")
        json.dump({"ww-57952305": {"evidence": phrase}}, open(d + "/overrides/closure_auto_undone.json", "w"))
        return d
    def test_exact_gallery_wording_is_locked(self):
        d = self._root(self.PHRASE)
        self.assertTrue(C.evidence_is_locked("ww-57952305", self.GALLERY, d))
        # typographic vs ASCII apostrophe still matches the same locked wording
        self.assertTrue(C.evidence_is_locked("ww-57952305", self.GALLERY.replace("’", "'"), d))
    def test_different_closed_wording_still_applies(self):
        d = self._root(self.PHRASE)
        self.assertFalse(C.evidence_is_locked("ww-57952305", self.VENUE, d))
        self.assertFalse(C.evidence_is_locked("ww-99999999", self.GALLERY, d))
    def test_check_all_skips_only_the_locked_wording(self):
        d = self._root(self.PHRASE)
        old = C._repo_root
        C._repo_root = lambda: d
        try:
            page = "Please note, The Vivarium and Nature’s Library are now closed until May 2027. Free entry Manchester Museum, M13 9PL."
            items = [{"id": "ww-57952305", "name": "Manchester Museum", "postcode": "M13 9PL", "website": "https://museum.example/"}]
            self.assertEqual(C.check_all(items, fetcher=lambda u: (u, page), today=T), {})
            closed = [{"id": "ww-57952305", "name": "Manchester Museum", "postcode": "M13 9PL", "website": "https://museum.example/"}]
            self.assertEqual(set(C.check_all(closed, fetcher=lambda u: (u, self.VENUE), today=T)), {"ww-57952305"})
        finally:
            C._repo_root = old
    def test_repo_lock_matches_the_gallery_sentence(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertTrue(C.evidence_is_locked("ww-57952305", self.GALLERY, root))
        self.assertFalse(C.evidence_is_locked("ww-57952305", self.VENUE, root))

if __name__ == "__main__":
    unittest.main()

