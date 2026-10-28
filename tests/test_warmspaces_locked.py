"""Bot 3 warm spaces fixes (28 Oct 2026): locked overrides survive the feed refresh, remove nothing, and are on Dean's review list.
Only fixes confirmed on the venue's own website are applied; the rest are held (unchanged) for Dean. No phone changes."""
import json, os, sys, copy, unittest
from urllib.parse import urlparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ws_locked

def published():
    t = open(os.path.join(ROOT, "warmspaces.js"), encoding="utf-8").read()
    return {x["id"]: x for x in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}

LOCKED = ws_locked.load(os.path.join(ROOT, ws_locked.PATH))
HELD = ws_locked.load_held(os.path.join(ROOT, ws_locked.PATH))
IDS = ["ww-65070433", "ww-55473488", "ww-55473766"]
HELD_IDS = ["ww-63065216"]
PHONES = {"ww-65070433": ("07523 424686", "07523424686"), "ww-55473488": ("01543 306147", "01543306147"),
          "ww-55473766": ("0115 962 2665", "01159622665"), "ww-63065216": ("", "")}  # stored numbers; changes need Dean
STRETHAM_FEED = {"hours": {"Thu": "14:00 - 16:00 Monthly"}, "website": "https://cambsacre.org.uk/cambridgeshire-community-hubs-network/", "postcode": "CB6 3LD"}

class Published(unittest.TestCase):
    def setUp(self): self.p = published()
    def test_all_four_still_listed(self):
        for i in IDS + HELD_IDS: self.assertIn(i, self.p)
    def test_wembley(self):
        x = self.p["ww-65070433"]
        self.assertEqual(x["address"], "Unit 17, 2 Station Grove, Wembley HA0 4AH")
        self.assertIn("Call before you go", x["notes"]); self.assertIn("until Summer 2026", x["notes"])
        self.assertIn("until Summer 2026", x["scheme_dates"]); self.assertIn("call before you go", x["scheme_dates"])
        self.assertTrue(x.get("call_before_you_go")); self.assertFalse(x.get("ended"))
        self.assertEqual(x["phone"], "07523 424686"); self.assertEqual(x["tel"], "07523424686")
        for f in ("notes", "scheme_dates"): self.assertNotIn("07523", x[f])  # number not on own site -> PHONES-FOR-DEAN.md
        self.assertEqual(x["hours"], {"Thu": "10:00 - 13:00 / 18:00 - 20:00"})
    def test_stretham_held_unchanged(self):  # not confirmed on its own site -> nothing changed, flagged for Dean
        x = self.p["ww-63065216"]
        for k, v in STRETHAM_FEED.items(): self.assertEqual(x[k], v, k)
        self.assertNotIn("locked_fix", x); self.assertNotIn("call_before_you_go", x)
        self.assertIn("first and third week", x["notes"])
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
        self.assertEqual(b["ww-63065216"], before[1])  # held, not applied
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
    def test_held_never_applied(self):
        self.assertEqual(sorted(e["id"] for e in HELD), HELD_IDS)
        self.assertFalse({e["id"] for e in HELD} & {e["id"] for e in LOCKED})
        self.assertFalse(any("set" in e for e in HELD))
        items = [dict(id=i, **copy.deepcopy(STRETHAM_FEED)) for i in HELD_IDS]; before = copy.deepcopy(items)
        self.assertEqual(ws_locked.apply(items), [])
        self.assertEqual(items, before)
    def test_applied_last_in_refresh(self):
        s = open(os.path.join(ROOT, "scripts", "build_warmspaces.py"), encoding="utf-8").read()
        a = s.index("ws_locked.apply(items)")
        self.assertGreater(a, s.index("phone_lock.guard(")); self.assertGreater(a, s.index("seasonal.apply("))
        self.assertLess(a, s.index('write_js(OUT, "WARMSPACES"'))

class ReviewList(unittest.TestCase):
    def test_every_entry_documented(self):
        for e in LOCKED:
            for k in ("id", "name", "set", "evidence_url", "own_site_url", "quote", "checked_on", "reason"): self.assertTrue(e.get(k) is not None and e.get(k) != "", (e["id"], k))
        for e in HELD:
            for k in ("id", "name", "own_site_url", "checked_on", "reason"): self.assertTrue(e.get(k), (e["id"], k))
    def test_evidence_is_the_venues_own_site(self):
        p = published(); host = lambda u: urlparse(u if "//" in u else "https://" + u).netloc.lower().removeprefix("www.")
        for e in LOCKED:
            self.assertEqual(e["evidence_url"], e["own_site_url"], e["id"])
            self.assertEqual(host(e["own_site_url"]), host(p[e["id"]]["website"]), e["id"])
    def test_no_phone_changes(self):
        for e in LOCKED + HELD:
            for k in ("phone", "tel"): self.assertNotIn(k, e.get("set", {})); self.assertNotIn(k, e.get("proposed", {}))
        p = published()
        for i, (phone, tel) in PHONES.items(): self.assertEqual((p[i]["phone"], p[i]["tel"]), (phone, tel), i)
        d = open(os.path.join(ROOT, "PHONES-FOR-DEAN.md"), encoding="utf-8").read()
        self.assertIn("Wembley Creative Community Hub (ww-65070433)", d); self.assertIn("07523 424686", d)
    def test_on_deans_review_list(self):
        md = open(os.path.join(ROOT, "reports", "layers_review.md"), encoding="utf-8").read()
        for e in LOCKED: self.assertIn(f"LOCKED FIX **{e['name']}** ({e['id']})", md)
        for e in HELD: self.assertIn(f"HELD, NOT APPLIED **{e['name']}** ({e['id']})", md)
        self.assertIn("CB6 3ND", md)
        lines = ws_locked.review_lines(LOCKED, HELD)
        self.assertEqual(sum(l.startswith("- LOCKED FIX") for l in lines), len(LOCKED))
        self.assertEqual(sum(l.startswith("- HELD, NOT APPLIED") for l in lines), len(HELD))

if __name__ == "__main__": unittest.main()
