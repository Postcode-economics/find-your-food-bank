"""Dean 4 Nov 2026: hand-set card values must survive every later refresh. Runs the shelter build's lock stage
(hours normalising -> place_lock.protect with the real overrides) twice in a row: run 1 against the stale
2 Nov published copy, run 2 with run 1's output as the published baseline. The times check returns only
differs_review / unreachable / none_published (nothing auto-applied). Every stated manual address, postcode,
hours and referral on the 36 man-ss- cards and Crisis Skylight Oxford must still be there after run 2.
Temp folders only; never writes real report or data files."""
import copy, json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock, hours_norm

IDS = lambda m: [r for r in m if str(r.get("id", "")).startswith("man-ss-") or r.get("id") == "man-crisis-skylight-oxford"]
TLOG_STATES = ("differs_review", "unreachable", "none_published")

def stated(v):
    return place_lock._stated(v)

class TwoRefreshes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "reports"))
        self.man = IDS(json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json"), encoding="utf-8")))
        self.hand = place_lock.hands(ROOT, "shelters")

    def build(self, published):
        items = copy.deepcopy(self.man)  # this run's rows as the build carries them before the lock
        hours_norm.apply(items, "hours")
        tlog = {x["id"]: {"status": TLOG_STATES[i % 3]} for i, x in enumerate(items)}
        keep = [i for i, r in tlog.items() if r.get("auto_applied")]
        place_lock.protect(items, published, self.hand, self.tmp, "shelters", keep_times=keep)
        return items

    def stale_published(self):
        old = copy.deepcopy(self.man)
        for x in old:  # the 2 Nov copy: other address wording, blank hours
            if x.get("address") and not x.get("no_pin"): x["address"] = x["address"] + " (old wording)"
            x["hours"] = ""
        return old

    def test_37_cards_keep_manual_values_after_two_runs(self):
        self.assertEqual(len(self.man), 37)
        run1 = self.build(self.stale_published())
        run2 = {x["id"]: x for x in self.build(copy.deepcopy(run1))}
        lost = []
        for m in self.man:
            got = run2[m["id"]]
            for f in ("address", "postcode", "hours", "referral"):
                want = place_lock.hand_value(got, f, self.hand.get(m["id"], {})) if f != "referral" else m.get("referral")
                if f == "referral" or not stated(want): want = m.get(f) if f == "referral" else want
                if want is None or not stated(want): continue
                if json.dumps(got.get(f)) != json.dumps(want): lost.append((m["id"], f, want, got.get(f)))
            if m.get("no_pin"):
                for f in ("lat", "lng", "postcode"):
                    if f in got: lost.append((m["id"], f, "absent on no_pin", got[f]))
        self.assertEqual(lost, [])

if __name__ == "__main__":
    unittest.main()
