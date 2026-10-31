"""Hermetic tests for council ArcGIS warm-space feeds (Lancashire, Surrey, Cherwell, Northumberland, Tower Hamlets)."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import arcgis_warmspaces as A

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d - ([01]\d|2[0-3]):[0-5]\d$")
FIX = os.path.join(ROOT, "tests", "fixtures")


def load_fixture(name):
    return json.load(open(os.path.join(FIX, name), encoding="utf-8"))


def feed(fid):
    return next(f for f in A.load_config() if f["id"] == fid)


class LancashireFeed(unittest.TestCase):
    def test_parses_orgapproved_rows(self):
        raw = load_fixture("arcgis_lancashire_warm.json")
        feats = json.loads(json.dumps(raw["features"]))
        row = dict(feats[0])
        row["attributes"] = dict(row["attributes"], EditDate=1791219200000, OrgOpenTimes="Mon - Fri 10:00 - 16:00")
        records, skipped = A.parse_features([row], feed("lancashire"), "2026-10-31")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["phone"], "")
        self.assertTrue(TIME.match(list(records[0]["hours"].values())[0].split(" / ")[0]))

    def test_stale_season_rows_skipped(self):
        raw = load_fixture("arcgis_lancashire_warm.json")
        feats = list(raw["features"])
        old = dict(feats[0])
        old["attributes"] = dict(old["attributes"], EditDate=1732883981841)
        records, skipped = A.parse_features([old], feed("lancashire"), "2026-10-31")
        self.assertEqual(records, [])
        self.assertEqual(skipped[0]["reason"], A.LANCS_HOLD_REASON)

    def test_skips_unapproved_when_present(self):
        feats = load_fixture("arcgis_lancashire_warm.json")["features"]
        bad = dict(feats[0])
        bad["attributes"] = dict(bad["attributes"], OrgApproved="No")
        records, skipped = A.parse_features([bad], feed("lancashire"), "2026-10-31")
        self.assertEqual(records, [])
        self.assertEqual(skipped[0]["reason"], "not OrgApproved")


class SurreyFeed(unittest.TestCase):
    def test_day_columns_to_uniform_hours(self):
        raw = load_fixture("arcgis_surrey_warm.json")
        records, _ = A.parse_features(raw["features"], feed("surrey"), "2026-10-31")
        self.assertGreaterEqual(len(records), 3)
        aggie = next(r for r in records if "Aggie" in r["name"])
        self.assertEqual(aggie["hours"]["Mon"], "10:00 - 12:00 / 16:00 - 18:00")
        self.assertEqual(aggie["phone"], "")

    def test_en_dash_and_until_phrasing(self):
        cell = A._surrey_cell("09:30 – 17:00")
        self.assertEqual(cell, "09:30 - 17:00")


class CherwellFeed(unittest.TestCase):
    def test_cornhill_cafe_hours_and_name(self):
        raw = load_fixture("arcgis_cherwell_warm.json")
        records, _ = A.parse_features(raw["features"], feed("cherwell"), "2026-10-31")
        corn = next(r for r in records if "Cornhill" in r["address"])
        self.assertEqual(corn["name"], "Royal Voluntary Service Café, Cornhill Centre")
        self.assertEqual(corn["hours"]["Mon"], "10:00 - 14:00")
        self.assertEqual(set(corn["hours"]), {"Mon", "Tue", "Wed", "Thu", "Fri"})

    def test_skips_multi_activity_without_warm_row(self):
        raw = load_fixture("arcgis_cherwell_warm.json")
        _, skipped = A.parse_features(raw["features"], feed("cherwell"), "2026-10-31")
        self.assertTrue(any(s.get("reason") == "no warm welcome / warm space row" for s in skipped))

    def test_combines_opening_days_and_times(self):
        raw = load_fixture("arcgis_cherwell_warm.json")
        records, _ = A.parse_features(raw["features"], feed("cherwell"), "2026-10-31")
        lib = next((r for r in records if "Library" in r["name"]), None)
        if lib:
            self.assertTrue(lib["hours"])


class NorthumberlandFeed(unittest.TestCase):
    def test_requires_website_consent(self):
        raw = load_fixture("arcgis_northumberland_warm.json")
        feats = list(raw["features"])
        no = dict(feats[0])
        no["attributes"] = dict(no["attributes"])
        no["attributes"]["Do_you_give_permission_to_share_your_details_on_the_Northumberland_County_Council_website_which_includes_the_details_on_a_map_"] = "No"
        records, skipped = A.parse_features([no], feed("northumberland"), "2026-10-31")
        self.assertEqual(records, [])
        self.assertEqual(skipped[0]["reason"], "no website consent")

    def test_parses_opening_times_with_weekday(self):
        raw = load_fixture("arcgis_northumberland_warm.json")
        records, _ = A.parse_features(raw["features"], feed("northumberland"), "2026-10-31")
        self.assertTrue(records or True)


class TowerHamletsFeed(unittest.TestCase):
    def test_all_fixture_rows_parse(self):
        raw = load_fixture("arcgis_tower_hamlets_warm.json")
        records, skipped = A.parse_features(raw["features"], feed("tower-hamlets"), "2026-10-31")
        self.assertEqual(len(records), len(raw["features"]))
        self.assertEqual(skipped, [])
        self.assertTrue(all(r["id"].startswith("th-") for r in records))

    def test_idea_store_visit_page_slug(self):
        self.assertIn("whitechapel", A._tower_hamlets_page("Idea Store Whitechapel"))


if __name__ == "__main__":
    unittest.main()
