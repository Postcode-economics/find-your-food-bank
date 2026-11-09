"""Plan 1.3: official feed finder drafts proposals only (rule 59, explicit 2026-27 dates)."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import feed_finder as F


class Season(unittest.TestCase):
    def test_explicit_2026_27_counts(self):
        self.assertTrue(F.season_evidence("Warm spaces 2026-27 open from October"))
        self.assertTrue(F.season_evidence("Winter 2026/27 list"))
        self.assertTrue(F.season_evidence("From 1 September 2026"))

    def test_edit_date_alone_does_not_count(self):
        self.assertEqual(F.season_evidence("Page updated 8 November 2026"), "")
        self.assertEqual(F.season_evidence("Last modified 2025-11-01"), "")


class Probe(unittest.TestCase):
    def test_skips_city_with_registered_feed(self):
        feeds = [{"id": "brighton-hove", "url": "https://gis.brighton-hove.gov.uk/x", "website": "https://www.brighton-hove.gov.uk/y"}]
        covered = F.covered_hosts(feeds)
        out = F.probe_city({"name": "Brighton and Hove"}, ["www.brighton-hove.gov.uk"], lambda u: {"ok": False}, covered)
        self.assertEqual(out["status"], "already_have_feed")
        self.assertFalse(out["needs_spot_check"])

    def test_proposal_requires_season_for_season_ok(self):
        pages = {
            "https://www.glasgow.gov.uk/warm-spaces": {
                "ok": True, "url": "https://www.glasgow.gov.uk/warm-spaces",
                "final_url": "https://www.glasgow.gov.uk/warm-spaces",
                "text": "<html>" + ("Warm spaces across Glasgow for winter 2026-27. " * 5) + "https://services.arcgis.com/x/arcgis/rest/services/Warm/FeatureServer/0/query</html>",
                "error": "",
            }
        }
        def fetch(u):
            return pages.get(u, {"ok": False, "url": u, "final_url": u, "text": "", "error": "no"})
        out = F.probe_city({"name": "Glasgow"}, ["www.glasgow.gov.uk"], fetch, set())
        self.assertEqual(out["status"], "proposal")
        self.assertTrue(out["needs_spot_check"])
        self.assertTrue(out["season_ok"])
        self.assertIn("FeatureServer", out["feed_url"])

    def test_no_publish_side_effects(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "overrides"))
            # minimal feeds file
            open(os.path.join(td, "overrides", "arcgis_warmspaces.json"), "w").write('{"feeds":[]}\n')
            # stub city list via monkeypatch cities arg
            cities = [{"name": "Belfast", "lat": 54.6, "lng": -5.9}]
            def fetch(u):
                return {"ok": False, "url": u, "final_url": u, "text": "", "error": "x"}
            # Point FEEDS at temp
            old = F.FEEDS
            try:
                F.FEEDS = os.path.join(td, "overrides", "arcgis_warmspaces.json")
                report = F.run(cities=cities, fetcher=fetch, root=td, write=True)
            finally:
                F.FEEDS = old
            self.assertEqual(report["summary"]["cities"], 1)
            self.assertTrue(os.path.exists(os.path.join(td, "reports", "official_source_proposals.json")))
            # overrides untouched beyond what we wrote
            self.assertEqual(json.load(open(os.path.join(td, "overrides", "arcgis_warmspaces.json"))), {"feeds": []})


if __name__ == "__main__":
    unittest.main()
