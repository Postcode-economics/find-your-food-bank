"""Bot 3 warm spaces fixes (28 Oct 2026): locked overrides survive the feed refresh, remove nothing, and are on Dean's review list."""
import json, os, sys, copy, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ws_locked

def published():
    t = open(os.path.join(ROOT, "warmspaces.js"), encoding="utf-8").read()
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}

LOCKED = ws_locked.load(os.path.join(ROOT, ws_locked.PATH))
IDS = ["ww-65070433", "ww-63065216", "ww-55473488", "ww-55473766"]

class Published(unittest.TestCase):
    def setUp(self): self.p = published()
    def test_all_four_still_listed(self):
        for i in IDS: self.assertIn(i, self.p)
    def test_wembley(self):
        x = self.p["ww-65070433"]
        self.assertEqual(x["address"], "Unit 17, 2 Station Grove, Wembley HA0 4AH")
        self.assertIn("Call before you go: 07523 424686", x["notes"])
        self.assertIn("until Summer 2026", x["scheme_dates"]); self.assertIn("call before you go", x["scheme_dates"])
        self.assertTrue(x.get("call_before_you_go")); self.assertFalse(x.get("ended"))
        self.assertEqual(x["phone"], "07523 424686")
    def test_stretham(self):
        x = self.p["ww-63065216"]
        self.assertEqual(x["hours"], {"Thu": "14:00 - 16:00 (1st & 3rd Thursday)"})
        self.assertNotIn("Monthly", json.dumps(x["hours"]))
        self.assertEqual(x["website"], "https://www.strethamparishcouncil.gov.uk/community/")
        self.assertEqual(x["postcode"], "CB6 3LD")  # not proven -> unchanged, flagged for Dean
    def test_wolverhampton(self):
        x = self.p["ww-55473488"]
        self.assertNotIn("2023", x["notes"]); self.assertEqual(x["scheme_start"], "")
        self.assertIn("Mon", x["notes"]); self.assertIn("Fri", x["notes"])
        self.assertEqual(x["hours"], {"Mon": "09:30 - 12:30", "Fri": "09:30 - 12:00"})
    def test_trinity_ended_not_removed(self):
        x = self.p["ww-55473766"]
        self.assertTrue(x["ended"]); self.assertEqual(x["hours"], {})
        self.assertIn("has come to an end", x["scheme_dates"]); self.assertIn("has come to an end", x["notes"])

class SurvivesRefresh(unittest.TestCase):
    def feed(self):  # what the Warm Welcome feed gives back on a refresh
        return [{"id": "ww-65070433", "address": "Unit 17, Wembley, Middlesex HA0 4AH", "notes": "feed", "hours": {"Thu": "10:00 - 13:00"}, "scheme_dates": "Not stated by source", "ended": False},
                {"id": "ww-63065216", "hours": {"Thu": "14:00 - 16:00 Monthly"}, "website": "https://cambsacre.org.uk/x", "postcode": "CB6 3LD"},
                {"id": "ww-55473488", "notes": "**Open from 6th November 2023.", "scheme_start": "2023-11-06", "hours": {"Mon": "09:30 - 12:30"}},
                {"id": "ww-55473766", "hours": {"Wed": "13:15 - 15:00"}, "ended": False, "scheme_dates": "Not stated by source"},
                {"id": "ww-other", "notes": "untouched"}]
    def test_reapplied_over_feed(self):
        items = self.feed(); before = copy.deepcopy(items)
        self.assertEqual(sorted(ws_locked.apply(items, LOCKED)), sorted(IDS))
        self.assertEqual(len(items), len(before))
        b = {x["id"]: x for x in items}
        self.assertEqual(b["ww-55473766"]["hours"], {}); self.assertTrue(b["ww-55473766"]["ended"])
        self.assertNotIn("Monthly", json.dumps(b["ww-63065216"]["hours"]))
        self.assertEqual(b["ww-55473488"]["scheme_start"], "")
        self.assertEqual(b["ww-55473488"]["hours"], {"Mon": "09:30 - 12:30"})  # times not in the lock stay the feed's
        self.assertIn("Station Grove", b["ww-65070433"]["address"])
        self.assertEqual(b["ww-other"], before[-1])
    def test_never_adds_or_removes(self):
        items = [{"id": "ww-other"}]
        self.assertEqual(ws_locked.apply(items, LOCKED), []); self.assertEqual(items, [{"id": "ww-other"}])
    def test_only_known_fields(self):
        items = [{"id": "a", "phone": "1"}]
        ws_locked.apply(items, [{"id": "a", "name": "x", "set": {"phone": "999", "notes": "n"}}])
        self.assertEqual(items[0]["phone"], "1"); self.assertEqual(items[0]["notes"], "n")
    def test_applied_last_in_refresh(self):
        s = open(os.path.join(ROOT, "scripts", "build_warmspaces.py"), encoding="utf-8").read()
        a = s.index("ws_locked.apply(items)")
        self.assertGreater(a, s.index("phone_lock.guard(")); self.assertGreater(a, s.index("seasonal.apply("))
        self.assertLess(a, s.index('write_js(OUT, "WARMSPACES"'))

class ReviewList(unittest.TestCase):
    def test_every_entry_documented(self):
        for e in LOCKED:
            for k in ("id", "name", "set", "evidence_url", "quote", "checked_on", "reason"): self.assertTrue(e.get(k) is not None and e.get(k) != "", (e["id"], k))
    def test_on_deans_review_list(self):
        md = open(os.path.join(ROOT, "reports", "layers_review.md"), encoding="utf-8").read()
        for e in LOCKED: self.assertIn(f"LOCKED FIX **{e['name']}** ({e['id']})", md)
        self.assertIn("CB6 3ND", md)
        lines = ws_locked.review_lines(LOCKED)
        self.assertEqual(sum(l.startswith("- LOCKED FIX") for l in lines), len(LOCKED))

if __name__ == "__main__": unittest.main()
