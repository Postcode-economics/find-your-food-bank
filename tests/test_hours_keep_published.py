"""An uncertain or failed hours read must never overwrite already-published hours.

Covers leftover 'Not stated' overlays (the First Stop Centre / Braintree wipe pattern)
and still lets a confirmed two-run change through. No new locks. Temp folders only.
"""
import os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import place_lock
import refresh_guard as g

# The published timetable that was wiped on 9 Nov when a leftover overlay
# "Not stated" was treated as a matching hand value and as "has times".
PUBLISHED_HOURS = {
    "Mon": "10:30 - 13:30",
    "Tue": "10:30 - 13:30",
    "Thu": "10:30 - 13:30",
    "Fri": "10:30 - 13:30",
}
CONFIRMED_HOURS = {
    "Mon": "09:00 - 12:00",
    "Wed": "09:00 - 12:00",
}
FS_ID = "man-first-stop-centre"


def _pub(**extra):
    item = {"id": FS_ID, "name": "First Stop Centre", "hours": dict(PUBLISHED_HOURS)}
    item.update(extra)
    return item


class HoursKeepPublished(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "reports"))

    def test_uncertain_read_keeps_published_hours(self):
        """(a) An unconfirmed or failed read must not replace published hours."""
        for new_hours in ("Not stated", "", None):
            with self.subTest(new_hours=new_hours):
                published = _pub()
                item = _pub()
                if new_hours is None:
                    item.pop("hours", None)
                else:
                    item["hours"] = new_hours
                place_lock.protect([item], [published], {}, self.root, "shelters")
                self.assertEqual(item["hours"], PUBLISHED_HOURS)

                # refresh_guard is the second backstop (times "vanished")
                new = _pub()
                if new_hours is None:
                    new.pop("hours", None)
                else:
                    new["hours"] = new_hours
                out, rep = g.guard("shelters", [published], [new])
                self.assertEqual(out[0]["hours"], PUBLISHED_HOURS)
                self.assertEqual(rep["times"], [FS_ID])

    def test_confirmed_change_still_progresses(self):
        """(b) A timetable the times gate confirmed this run still applies."""
        published = _pub()
        item = _pub(hours=dict(CONFIRMED_HOURS))
        # Leftover overlay default must not block a confirmed apply.
        hand = {FS_ID: {"hours": "Not stated"}}
        place_lock.protect(
            [item], [published], hand, self.root, "shelters", keep_times=(FS_ID,)
        )
        self.assertEqual(item["hours"], CONFIRMED_HOURS)

        # The guard must not treat a real new timetable as times vanishing.
        out, rep = g.guard("shelters", [published], [_pub(hours=dict(CONFIRMED_HOURS))])
        self.assertEqual(out[0]["hours"], CONFIRMED_HOURS)
        self.assertEqual(rep["times"], [])

    def test_leftover_not_stated_overlay_keeps_published_hours(self):
        """(c) First Stop Braintree pattern: leftover 'Not stated' in the
        manual/verified overlay, kept through an unconfirmed read, must not
        skip restore of the published day table."""
        published = _pub()
        item = _pub(hours="Not stated")
        # hands() used to store 'Not stated' because it is a non-empty string.
        # Build the allowed map the way hands() does, from overlay-like records.
        allowed = {}
        place_lock._add_hand(allowed, FS_ID, {"hours": "Not stated", "address": "29 Bocking End, Braintree"})
        self.assertNotIn("hours", allowed.get(FS_ID, {}), "Not stated must not count as a hand timetable")
        # Even if a caller still passes 'Not stated' in the allowed map:
        stale_allowed = {FS_ID: {"hours": "Not stated"}}
        place_lock.protect([item], [published], stale_allowed, self.root, "shelters")
        self.assertEqual(item["hours"], PUBLISHED_HOURS)

        out, rep = g.guard("shelters", [published], [_pub(hours="Not stated")])
        self.assertEqual(out[0]["hours"], PUBLISHED_HOURS)
        self.assertEqual(rep["times"], [FS_ID])

    def test_stated_hand_timetable_still_wins(self):
        published = _pub()
        item = _pub(hours="Not stated")
        hand = {FS_ID: {"hours": "Staffed 24/7"}}
        place_lock.protect([item], [published], hand, self.root, "shelters")
        self.assertEqual(item["hours"], "Staffed 24/7")

    def test_warm_spaces_share_the_same_helpers(self):
        published = {"id": "ww-test", "name": "Hall", "hours": dict(PUBLISHED_HOURS)}
        item = dict(published, hours="Not stated")
        place_lock.protect([item], [published], {"ww-test": {"hours": "Not stated"}}, self.root, "warmspaces")
        self.assertEqual(item["hours"], PUBLISHED_HOURS)
        out, rep = g.guard("warmspaces", [published], [dict(published, hours="Not stated")])
        self.assertEqual(out[0]["hours"], PUBLISHED_HOURS)
        self.assertEqual(rep["times"], ["ww-test"])

    def test_food_bank_not_stated_is_not_has_times(self):
        published = {
            "id": "fb-test",
            "name": "F",
            "lat": 1,
            "lng": 1,
            "phone": "1",
            "opening_times": {"raw": "Mon 10-12", "structured": {"mon": [["10:00", "12:00"]]}},
        }
        self.assertFalse(g.has_times("foodbanks", {"opening_times": {"raw": "Not stated"}}))
        self.assertFalse(g.has_times("foodbanks", {"opening_times": {"status": "NOT_FOUND"}}))
        new = dict(published, opening_times={"raw": "Not stated"})
        out, rep = g.guard("foodbanks", [published], [new])
        self.assertEqual(out[0]["opening_times"]["raw"], "Mon 10-12")
        self.assertEqual(rep["times"], ["fb-test"])

    def test_existing_lock_and_privacy_tests_are_unchanged(self):
        """(d) This PR must not edit the existing lock or privacy tests."""
        names = (
            "test_privacy_check.py",
            "test_privacy_check_live.py",
            "test_doorway_hours_lock.py",
            "test_hand_values_survive_two_refreshes.py",
        )
        import subprocess
        # Compare to origin/main (this branch starts from it; those files must be identical).
        # A checkout without an origin/main ref (shallow or single-branch clone) has nothing to compare: skip, not fail.
        has_ref = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main^{commit}"],
                                 cwd=ROOT, capture_output=True).returncode == 0
        if not has_ref:
            self.skipTest("origin/main ref not available in this checkout")
        for name in names:
            rel = "tests/" + name
            rc = subprocess.run(
                ["git", "diff", "--exit-code", "origin/main", "--", rel],
                cwd=ROOT,
                capture_output=True,
            )
            self.assertEqual(rc.returncode, 0, "%s was changed" % rel)


if __name__ == "__main__":
    unittest.main()
