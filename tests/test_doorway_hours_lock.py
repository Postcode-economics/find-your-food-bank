"""Doorway Nuneaton (sh:man-doorway-young-people-16-25): doorway.org.uk/contact lists "Office Opening Hours ...
Friday: 9:00am-4:30pm". Those are office hours, not opening times. The refresh applied Fri 09:00-16:30 twice (5 Nov);
it was undone with scripts/times_revert.py and that exact change is locked (rule 50). Other values are not blocked."""
import os, sys, json, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import discover as D
KEY, IID = "sh:man-doorway-young-people-16-25", "man-doorway-young-people-16-25"
WRONG = {"fri": [["09:00", "16:30"]]}
SRC = "https://www.doorway.org.uk/contact"
PAGE = ("Office Opening Hours\nMonday to Thursday: 9:00am-5:00pm\nFriday: 9:00am-4:30pm\n"
        "Doorway\n25-27 Dugdale Street, Nuneaton, Warwickshire, CV11 5QJ\n02476 345583")
def blocked(): return json.load(open(os.path.join(ROOT, D.XC_BLOCK)))
def item(hours="Not stated"):
    return {"id": IID, "name": "Doorway (young people 16-25)", "postcode": "CV11 5QJ", "website": SRC, "hours": hours}
def reasons(new_st, blk):
    new = {"Fri": "09:00 - 16:30"} if new_st == WRONG else {"Mon": "10:00 - 12:00"}
    new = dict(new); new["structured"] = new_st
    seen = {KEY: {"sig": D._tsig(new_st), "source_url": SRC, "run_at": "2026-11-01T22:19:00+00:00"}}
    return D.times_gate_reasons(item(), "sh", "hours", new, [PAGE], {"final_url": SRC}, seen, blk, True,
                                "2026-11-08T04:29:00+00:00", own_sites={}, overrides={})
class DoorwayLock(unittest.TestCase):
    def test_lock_is_the_exact_wrong_signature(self):
        self.assertEqual(blocked().get(KEY), D._tsig(WRONG))
    def test_wrong_friday_apply_cannot_return(self):
        self.assertIn("this change was undone by Dean; not re-applied", reasons(WRONG, blocked()))
    def test_lock_blocks_only_that_value(self):
        self.assertNotIn("this change was undone by Dean; not re-applied", reasons({"mon": [["10:00", "12:00"]]}, blocked()))
    def test_published_card_not_stated(self):
        s = open(os.path.join(ROOT, "shelters.js"), encoding="utf-8").read()
        d = json.loads(s[s.index("{"):s.rindex("}") + 1])
        it = next(i for i in d["items"] if i["id"] == IID)
        self.assertEqual(it["hours"], "Not stated")
    def test_apply_log_marked_reverted(self):
        try:
            log = json.load(open(os.path.join(ROOT, "reports", "times_auto_applied.json")))
        except FileNotFoundError:
            raise unittest.SkipTest("Private working file is not available in the public checkout")
        recs = [r for r in log if r.get("id") == IID and r.get("kind") == "sh" and r.get("path") == "cross_check"]
        self.assertTrue(recs and all(r.get("reverted") for r in recs if r.get("new_structured") == WRONG))
if __name__ == "__main__": unittest.main()
