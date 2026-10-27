"""Check and refresh clock times, and the add/remove guards, stay put. Signals only reorder within a run."""
import os, json, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CRONS = {
    ".github/workflows/refresh.yml": "29 4,12,20 * * *",
    ".github/workflows/refresh-shelters.yml": "41 4,12,20 * * *",
    ".github/workflows/refresh-warmspaces.yml": "53 4,12,20 * * *",
    ".github/workflows/sweep-daily.yml": "5 3,11,19 * * *",
    ".github/workflows/swep-daily.yml": "0 5 * * *",
    ".github/workflows/fb-page-check.yml": "40 6 * * *",
    ".github/workflows/watchdog.yml": "17 * * * *",
    ".github/workflows/deploy-check.yml": "15 6 * * *",
}
AUTOMATIC = [
    "opening times", "temporary closures", "voucher/walk-in flips", "clear single new phone on own site",
    "warm space end dates", "SWEP open/close", "moved link to same organisation",
]

def assert_schedule_and_guards():
    for rel, cron in CRONS.items():
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        if cron not in text:
            raise AssertionError("%s clock changed (expected %s)" % (rel, cron))
    rules = json.load(open(os.path.join(ROOT, "overrides", "auto_apply_rules.json"), encoding="utf-8"))
    for layer in ("foodbanks", "shelters", "warmspaces"):
        if rules["add_new_places"][layer]:
            raise AssertionError("add_new_places.%s must stay false" % layer)
    if rules["remove_confirmed_closures"]:
        raise AssertionError("remove_confirmed_closures must stay false")
    if rules["confirm_runs"] != 2:
        raise AssertionError("confirm_runs changed")
    # Dean 27 Oct 2026 07:20 GMT: strict times auto-apply switched on. Pinned so it can't flip silently either way.
    if rules.get("times_auto_apply") is not True:
        raise AssertionError("times_auto_apply changed (Dean set it on, strict, 27 Oct)")
    if sorted(rules["automatic"]) != sorted(AUTOMATIC):
        raise AssertionError("automatic list changed")
    import sys
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import learning
    if learning.FLOOR_DAYS != 7:
        raise AssertionError("weekly minimum check changed")
    if learning.BOOST_CAP != 3.0:
        raise AssertionError("combined boost cap changed")

class Guards(unittest.TestCase):
    def test_schedule_and_guards_unchanged(self):
        assert_schedule_and_guards()

if __name__ == "__main__": unittest.main()
