"""Guard: incident rest-centre watch state survives a job restart without putting
internal files in the public repo (rule 97). Rebuild from the already-public live
file when gitignored logs/ are empty. Do NOT use Actions cache or artifacts on this
public repo (fork PRs can read the cache; artifacts are downloadable). Rule 34: this
guard must not be loosened."""
import datetime, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyyaml"])
    import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
WF = os.path.join(ROOT, ".github", "workflows", "incident-rest-centre-watch.yml")
NOW = datetime.datetime(2026, 11, 9, 14, 0, tzinfo=datetime.timezone.utc)

CARD = {
    "badge": "Rest centre (council-run)",
    "name": "Riverside Hall",
    "open_until": "2099-01-01T12:00:00+00:00",
    "address": "BN17 5AA",
    "live": True,
    "opened_by": "Arun District Council",
    "source_url": "https://example.gov.uk/emergencies/riverside",
    "category": "incident_rest_centre",
    "council": "Arun District Council",
    "lad": "E07000224",
    "quote": "A rest centre is open at Riverside Hall.",
}


class HydrateFromPublicLive(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "overrides"))
        os.makedirs(os.path.join(self.d, "logs"))
        json.dump({"public": True}, open(os.path.join(self.d, "overrides", "incident_rest_centre_mode.json"), "w"))

    def _write_live(self, cards):
        import incident_rest_centre_live as live
        payload = {
            "public": True,
            "generated": NOW.isoformat(),
            "category": "incident_rest_centre",
            "cards": cards,
            "councils": {"E07000224": "Arun District Council"} if cards else {},
        }
        json.dump(payload, open(os.path.join(self.d, live.OUT_JSON), "w"))

    def test_empty_state_rebuilds_from_live_cards(self):
        import incident_rest_centre_live as live
        import incident_rest_centre_switch_on as irso
        self._write_live([CARD])
        note = live.hydrate_from_public_live(self.d, now=NOW)
        self.assertTrue(note.startswith("hydrated"), note)
        state = live.load_state(os.path.join(self.d, live.STATE))
        self.assertEqual(len(state.get("incidents") or {}), 1)
        urls = []
        for v in (state.get("incidents") or {}).values():
            urls.append((v.get("card") or {}).get("source_url") or v.get("url"))
        self.assertEqual(urls, [CARD["source_url"]])
        snap = irso.load_snapshot(self.d)
        self.assertEqual(len(snap), 1)
        self.assertEqual(snap[0].get("url"), CARD["source_url"])
        self.assertTrue((snap[0].get("rest_centre") or {}).get("active"))

    def test_existing_state_is_left_alone(self):
        import incident_rest_centre_live as live
        self._write_live([CARD])
        prior = {"incidents": {"keep": {"council": "X", "url": "https://keep.example", "card": {"name": "Keep"}}}}
        live.save_state(prior, os.path.join(self.d, live.STATE))
        note = live.hydrate_from_public_live(self.d, now=NOW)
        self.assertEqual(note, "state-present")
        state = live.load_state(os.path.join(self.d, live.STATE))
        self.assertIn("keep", state.get("incidents") or {})

    def test_no_cards_is_a_no_op(self):
        import incident_rest_centre_live as live
        self._write_live([])
        note = live.hydrate_from_public_live(self.d, now=NOW)
        self.assertEqual(note, "no-cards")
        state = live.load_state(os.path.join(self.d, live.STATE))
        self.assertEqual(state.get("incidents") or {}, {})

    def test_watch_rescans_hydrated_live_card_without_a_warning(self):
        """After a job restart with empty logs/, the public live file alone supplies re-scan URLs.

        Does not call the full watch run (that opens GitHub issues); other watch tests cover
        fetch+switch-on with a fake gh. This guard locks the hydrate → live_source_urls path.
        """
        import incident_rest_centre_live as live
        import incident_rest_centre_watch as W
        self._write_live([CARD])
        note = live.hydrate_from_public_live(self.d, now=NOW)
        self.assertTrue(note.startswith("hydrated"), note)
        urls = W.live_source_urls(self.d)
        self.assertEqual(urls, [CARD["source_url"]])
        state = live.load_state(os.path.join(self.d, live.STATE))
        self.assertTrue(state.get("incidents"), "hydrated state must remain")


class WorkflowNoPublicCache(unittest.TestCase):
    def test_workflow_has_no_actions_cache_or_artifacts(self):
        text = open(WF, encoding="utf-8").read()
        self.assertNotIn("actions/cache", text)
        self.assertNotIn("actions/upload-artifact", text)
        self.assertNotIn("actions/download-artifact", text)
        self.assertNotIn("upload-artifact", text)
        self.assertNotIn("download-artifact", text)

    def test_hydrate_is_wired_in_watch_and_loop(self):
        live = open(os.path.join(ROOT, "scripts", "incident_rest_centre_live.py"), encoding="utf-8").read()
        watch = open(os.path.join(ROOT, "scripts", "incident_rest_centre_watch.py"), encoding="utf-8").read()
        loop = open(os.path.join(ROOT, "scripts", "incident_rest_centre_watch_loop.sh"), encoding="utf-8").read()
        self.assertIn("def hydrate_from_public_live", live)
        self.assertIn("hydrate_from_public_live", watch)
        self.assertIn("--hydrate-from-live", loop)
        self.assertIn("incident_rest_centre_live.json", live)

    def test_logs_stay_gitignored_and_live_file_is_tracked(self):
        gi = (Path(ROOT) / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(any(line.strip() == "logs/" for line in gi.splitlines()), "logs/ must stay ignored (rule 97)")
        tracked = subprocess.check_output(
            ["git", "-C", ROOT, "ls-files", "incident_rest_centre_live.json", "incident_rest_centre_live.js"],
            text=True,
        )
        self.assertIn("incident_rest_centre_live.json", tracked)
        ignored = subprocess.check_output(
            ["git", "-C", ROOT, "check-ignore", "-v", "logs/incident_rest_centre_live_state.json"],
            text=True,
        )
        self.assertIn("logs/", ignored)

    def test_practice_max_checks_does_not_chain_and_concurrency_is_per_ref(self):
        with open(WF, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        self.assertEqual(data["concurrency"]["group"], "incident-rest-centre-watch-${{ github.ref }}")
        self.assertFalse(data["concurrency"]["cancel-in-progress"])
        on = data.get(True) or data.get("on") or {}
        wd = on.get("workflow_dispatch") or {}
        inputs = (wd.get("inputs") if isinstance(wd, dict) else {}) or {}
        self.assertIn("max_checks", inputs)
        chain = next(
            s for s in data["jobs"]["watch"]["steps"] if (s.get("name") or "").startswith("Start the next check")
        )
        cond = chain.get("if") or ""
        self.assertIn("max_checks", cond)
        self.assertIn("refs/heads/main", cond)


if __name__ == "__main__":
    unittest.main()
