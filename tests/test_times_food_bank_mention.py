"""Rule 21 for opening times (Dean 28 Oct 2026): times auto-apply only from the food bank's own page. A host church page
counts only when the food bank has no own site AND the page itself names the food bank. A page that never mentions a
food bank (or the listing's name) is held for Dean, on both the finder path and the refresh gate."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D, times_finder as TF
from test_times_crosscheck_gate import OLD, NEW_ST, R1, R2, ON, FILL, fetch, pg, item

CHURCH = "<html><body><h1>St Mary's Church</h1><p>Coffee and chat. St Mary's Hall, 1 High St, AB1 2CD. Thursday 2pm - 4pm.</p>%s</body></html>" % FILL
GOOD = {"status": "TIMES_FOUND", "structured": {"wed": [["10:00", "12:00"]]}, "raw": "Wednesday 10am-12pm",
        "source_url": "https://testfb.org.uk/opening-times", "pc_seen": ["AB12CD"], "reader": "times_finder", "checked_date": "2026-10-27"}
ITEM = {"id": "fb1", "name": "Test Foodbank", "postcode": "AB1 2CD", "website": "https://testfb.org.uk/"}
SEEN = {"fb1": {"sig": json.dumps(GOOD["structured"], sort_keys=True), "source_url": GOOD["source_url"], "run_at": "2026-10-27T03:00:00+00:00"}}


class Finder(unittest.TestCase):
    def why(self, **kw): return TF.strict_checks("fb1", dict(GOOD, _run_at="2026-10-27T11:00:00+00:00", **kw), ITEM, {}, SEEN, 1, {"pages": {}, "skip": {}})

    def test_named_page_passes(self):
        self.assertEqual(self.why(fb_mention=True), [])

    def test_page_without_a_mention_is_held(self):
        self.assertEqual(self.why(fb_mention=False), [D.NO_FB_MENTION])

    def test_a_result_with_no_recorded_mention_is_held(self):
        self.assertEqual(self.why(), [D.NO_FB_MENTION])

    def test_trussell_centre_cards_need_no_mention(self):
        self.assertEqual(self.why(reader="trussell_cards", matched_by="postcode"), [])

    def test_generic_records_the_mention(self):
        orig = TF.polite; self.addCleanup(setattr, TF, "polite", orig)
        it = dict(ITEM, website="https://stmarys.example.org/")
        for body, want in ((CHURCH, False), (CHURCH.replace("Coffee and chat", "Test Foodbank session"), True),
                           (CHURCH.replace("Coffee and chat", "Food parcels"), True)):
            TF.polite = lambda u, tries=3, b=body: (200, u, b) if not u.endswith(".xml") else (404, u, "")
            ot, _ = TF.generic([it], it["website"])["fb1"]
            self.assertIs(ot["fb_mention"], want, body[:120])


class RefreshGate(unittest.TestCase):
    def setUp(self): self.root = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.root, True)
    def twice(self, it, kind="fb", field="opening_times"):
        f = fetch({"https://x.org/": pg(CHURCH)})
        D.cross_check_times([dict(x) for x in it], kind, field, f, state_root=self.root, rules=ON, run_at=R1)
        return D.cross_check_times(it, kind, field, f, state_root=self.root, rules=ON, run_at=R2)

    def test_reason_on_its_own(self):
        seen = {"fb:a": {"sig": json.dumps(NEW_ST, sort_keys=True), "source_url": "https://x.org/", "run_at": R1}}
        g = D.times_gate_reasons(item(), "fb", "opening_times", {"structured": NEW_ST, "status": "TIMES_FOUND"}, [CHURCH], {"final_url": "https://x.org/"}, seen, {}, True, R2)
        self.assertEqual(g, [D.NO_FB_MENTION])

    def test_church_page_food_bank_times_never_applied(self):
        it = [item()]; log = self.twice(it)
        self.assertEqual(log["a"]["status"], "held_for_dean"); self.assertIn(D.NO_FB_MENTION, log["a"]["held"])
        self.assertEqual(it[0]["opening_times"], OLD)
        al = os.path.join(self.root, "reports", "times_auto_applied.json")
        self.assertFalse(os.path.exists(al) and json.load(open(al)))

    def test_shelter_hours_do_not_need_food_bank_wording(self):
        it = [item(opening_times=None, hours={"Tue": "10:00 - 12:00"})]; it[0].pop("opening_times")
        self.twice(it, kind="sh", field="hours")
        self.assertEqual(it[0]["hours"], {"Thu": "14:00 - 16:00"})


if __name__ == "__main__": unittest.main()
