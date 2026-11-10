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


class Winter2026IsLastSeason(unittest.TestCase):
    """Grok Bot 2 review (10 Nov): a bare "Winter 2026" label named LAST season's Lancashire list and was wrongly read as current."""

    def test_last_seasons_winter_2026_label_is_past(self):  # the real Lancashire heading
        self.assertEqual(S.row_season({"orgopentimes": "Warm Spaces Winter 2026 12th Jan - 30th Mar 2026"})[0], "past")
        self.assertEqual(S.row_season({"orgname": "Warm Spaces Winter 2026", "orgopentimes": "Mon 10-12"})[0], "undated")
        self.assertEqual(S.row_season({"orgopentimes": "Winter 2026"})[0], "undated")

    def test_explicit_2026_27_labels_still_current(self):
        for t in ("Winter 2026-27", "winter 2026/27", "Winter 2026-2027", "Warm spaces 2026–27", "2026-27 November to March"):
            self.assertEqual(S.row_season({"orgopentimes": t})[0], "current", t)

    def test_edit_metadata_date_is_not_the_season(self):
        self.assertEqual(S.row_season({"orgopentimes": "Mon 10-12", "orgnotes": "Last updated 12 September 2026"})[0], "undated")
        self.assertEqual(S.row_season({"orgopentimes": "Mon 10-12. Reviewed on 3 October 2026"})[0], "undated")
        # a real stated season date next to the metadata still counts
        self.assertEqual(S.row_season({"orgopentimes": "Weds from 5th November 2026", "orgnotes": "Updated 12 September 2026"}), ("current", "2026-11-05"))


class MergeWritesOnlyWhereTold(unittest.TestCase):
    """Grok Bot 2 review (10 Nov): the watcher must write to the caller's report root, never the real checkout from a test,
    and must only see the Lancashire rows of this merge_into run."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        import arcgis_warmspaces as A
        self.A = A
        self.real = [os.path.join(A.ROOT, "reports", "lancs_season.json"), os.path.join(A.ROOT, "logs", "arcgis_lancs_pending.json")]
        self.before = [os.path.getmtime(p) if os.path.exists(p) else None for p in self.real]

    def tearDown(self):
        shutil.rmtree(self.d)
        self.A._LANCS_SEEN.clear()

    def _real_untouched(self):
        after = [os.path.getmtime(p) if os.path.exists(p) else None for p in self.real]
        self.assertEqual(after, self.before, "merge_into wrote into the real checkout's reports/ or logs/")

    def _cfg(self):
        cfg = os.path.join(self.d, "feeds.json")
        lancs = next(x for x in self.A.load_config() if x["id"] == "lancashire")  # the real feed entry, read only
        json.dump({"feeds": [dict(lancs, url="https://example.invalid/FeatureServer/0")]}, open(cfg, "w"))
        return cfg

    def test_report_goes_to_report_root(self):
        A = self.A
        fx = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "arcgis_lancashire_warm.json"), encoding="utf-8"))
        row = dict(fx["features"][0])
        row["attributes"] = dict(row["attributes"], EditDate=1732883981841,  # last season's row, so it is held
                                 OrgOpenTimes="Mondays 10am - 1.30pm. Warm Spaces Winter 2026 12th Jan - 30th Mar 2026")
        body = json.dumps({"features": [row]})
        fresh = []
        A.merge_into(fresh, "2026-11-11", config_path=self._cfg(), pending_path=os.path.join(self.d, "none.json"),
                     getter=lambda url: body, report_root=self.d)
        doc = json.load(open(os.path.join(self.d, "reports", "lancs_season.json")))
        self.assertEqual(doc["counts"]["current"], 0)
        self.assertFalse(doc["lifts_hold"])
        self.assertEqual(fresh, [])  # still held
        self.assertTrue(os.path.exists(os.path.join(self.d, "logs", "arcgis_lancs_pending.json")))
        self._real_untouched()

    def test_earlier_parse_does_not_leak_into_merge(self):
        A = self.A
        A._LANCS_SEEN.update(features=[f(7, "Weds from 5th November 2026")], run_day="2026-11-01")
        empty = os.path.join(self.d, "empty.json")
        json.dump({"feeds": []}, open(empty, "w"))
        A.merge_into([], "2026-11-11", config_path=empty,
                     pending_path=os.path.join(self.d, "none.json"), getter=lambda url: "{}", report_root=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, "reports", "lancs_season.json")))
        self._real_untouched()


if __name__ == "__main__":
    unittest.main()
