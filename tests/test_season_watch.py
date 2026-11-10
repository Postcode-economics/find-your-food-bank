"""Plan 1.4 (9 Nov 2026): Lancashire season watcher. Reporting only; the hold is never lifted by it."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import season_watch as S


def f(oid, times, **k): return {"attributes": dict({"objectid": oid, "OrgApproved": "Yes", "OrgName": "Venue %d" % oid, "OrgOpenTimes": times}, **k)}


class Row(unittest.TestCase):
    def test_last_season_dates_are_past(self):  # the real 8 Nov Lancashire rows
        self.assertEqual(S.row_season({"orgopentimes": "Mondays 10 am - 2pm \n12th Jan 2026 - 30th March  2026 "})[0], "past")
        self.assertEqual(S.row_season({"orgopentimes": "Mondays 10am - 1.30pm 12th Jan - 30th Mar 2026"})[0], "past")

    def test_explicit_current_dates(self):
        self.assertEqual(S.row_season({"orgopentimes": "Tuesdays from 4th November 2026 to 31 March 2027"}), ("current", "2026-11-04"))
        self.assertEqual(S.row_season({"orgopentimes": "Mon 12th Jan - 30th Mar 2027"})[0], "current")
        self.assertEqual(S.row_season({"orgopentimes": "Warm space 2026/27, Weds 10-12"})[0], "current")
        self.assertEqual(S.row_season({"orgopentimes": "from 05/11/2026"})[0], "current")

    def test_edit_date_alone_is_not_enough(self):
        self.assertEqual(S.row_season({"orgopentimes": "Weds 10-12", "editdate": 1762000000000})[0], "undated")

    def test_address_numbers_are_not_a_season(self):
        self.assertEqual(S.row_season({"orgaddress": "26-27 High Street, Preston PR1 2AA", "orgopentimes": "Mon 10-12"})[0], "undated")

    def test_outside_window_not_current(self):
        self.assertNotEqual(S.row_season({"orgopentimes": "from 3 June 2027"})[0], "current")
        self.assertNotEqual(S.row_season({"orgopentimes": "1 August 2026 onwards"})[0], "current")


class Watch(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d)

    def test_not_ready_on_last_seasons_list(self):
        doc = S.write([f(1, "12th Jan - 30th Mar 2026"), f(2, "Mon 10-12")], "2026-11-09", self.d)
        self.assertFalse(doc["ready_for_spot_check"]); self.assertFalse(doc["lifts_hold"])
        self.assertIn("Still last season's list", open(os.path.join(self.d, "reports", "lancs_season.md")).read())

    def test_ready_gives_fixed_sample_and_never_lifts(self):
        feats = [f(i, "Weds from 5th November 2026") for i in range(12)] + [f(99, "x", OrgApproved="No")]
        a = S.write(feats, "2026-11-09", self.d); b = S.watch(feats, "2026-11-09")
        self.assertTrue(a["ready_for_spot_check"]); self.assertFalse(a["lifts_hold"])
        self.assertEqual(a["rows"], 12); self.assertEqual(len(a["spot_check"]), S.SAMPLE)
        self.assertEqual([r["objectid"] for r in a["spot_check"]], [r["objectid"] for r in b["spot_check"]])
        self.assertIn("rule 59", open(os.path.join(self.d, "reports", "lancs_season.md")).read())

    def test_publish_gate_hold_untouched(self):
        import publish_gate as P
        self.assertIn(P.LANCS_HOLD, P.warmspace_publish_holds({"id": "lancs-123"}))


if __name__ == "__main__":
    unittest.main()
