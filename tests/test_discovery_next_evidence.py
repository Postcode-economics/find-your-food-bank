"""Plan 1.2 wording follow-through: queued finds record the next evidence needed."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discovery_rules as DR

T = "2026-11-09"

class NextEvidence(unittest.TestCase):
    def test_foodbank_season_wording_points_at_own_site(self):
        nxt = DR.next_evidence(["directory listing only, with no 2026-27 season dates"], "foodbanks")
        self.assertIn("own site", nxt.lower())
        self.assertIn("no season", nxt.lower())

    def test_unreachable_own_site(self):
        self.assertIn("own site", DR.next_evidence(["own site unreachable (HTTP error)"], "foodbanks").lower())

    def test_record_attaches_next_evidence(self):
        r = tempfile.mkdtemp()
        os.makedirs(os.path.join(r, "reports"))
        open(os.path.join(r, "reports", "manual_review.md"), "w").write("# Manual\n")
        DR.record("foodbanks", T, [], [{"id": "fb1", "name": "Hive", "reasons": ["own site unreachable (HTTP error)"]}], [], root=r)
        q = json.load(open(os.path.join(r, "logs", "discovery_today_foodbanks.json")))["queued"]["fb1"]
        self.assertTrue(q.get("next_evidence"))
        self.assertIn("own site", q["next_evidence"].lower())
        mr = open(os.path.join(r, "reports", "manual_review.md")).read()
        self.assertIn("next:", mr)


class SweepQueue(unittest.TestCase):
    def test_sweep_queue_proposes_without_publishing(self):
        import follow_through as F
        import discover
        r = tempfile.mkdtemp()
        os.makedirs(os.path.join(r, "logs"))
        os.makedirs(os.path.join(r, "reports"))
        day = T
        queued = {
            "ws1": {
                "id": "ws1", "name": "Central Library", "postcode": "G1 1AB",
                "website": "https://libraries.example.gov.uk/warm-spaces",
                "reasons": ["directory listing only, with no 2026-27 season dates"],
            }
        }
        json.dump({"day": day, "runs": [], "added": [], "queued": queued, "rejected": {}},
                  open(os.path.join(r, "logs", "discovery_today_warmspaces.json"), "w"))
        venue = (
            "<html><body><h1>Central Library</h1>"
            "<p>G1 1AB. Warm space open Tuesday 10:00am - 4:00pm.</p>"
            "</body></html>"
        )
        def fetch(u):
            return {"http": 200, "final_url": u, "html": venue, "etag": "", "last_modified": "", "sha256": "x"}
        # Avoid real sleep
        out = F.sweep_queue(root=r, fetcher=fetch, limit=5, gap=0, render=False, day=day, layers=("warmspaces",))
        self.assertEqual(out["checked"], 1)
        # No overrides touched
        self.assertFalse(os.path.exists(os.path.join(r, "overrides")))
        # Seen recorded
        self.assertTrue(os.path.exists(os.path.join(r, "logs", "follow_through_queue_seen.json")))


if __name__ == "__main__":
    unittest.main()
