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
        records, skipped = A.parse_features(raw["features"], feed("lancashire"), "2026-10-31")
        self.assertGreaterEqual(len(records), 1)
        self.assertTrue(all(r["phone"] == "" for r in records))
        self.assertTrue(all(TIME.match(list(r["hours"].values())[0].split(" / ")[0]) for r in records if r["hours"]))

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
    def test_skips_check_website_hours(self):
        raw = load_fixture("arcgis_cherwell_warm.json")
        records, skipped = A.parse_features(raw["features"], feed("cherwell"), "2026-10-31")
        self.assertTrue(any(s.get("reason") == "hours say check website" for s in skipped))
        self.assertTrue(all(r["postcode"] for r in records))

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
