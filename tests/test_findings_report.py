"""Hermetic tests for scripts/findings_report.py (no live GitHub, temp roots only)."""
import json, os, shutil, sys, tempfile, unittest
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import findings_report as FR

RUN_START = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class FindingsReport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "reports"), exist_ok=True)
        os.makedirs(os.path.join(self.d, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.d, "overrides"), exist_ok=True)
        self.posted = []

        def fake_post(key, title, body):
            self.posted.append((key, title, body))

        self.post = fake_post

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_nothing_new_posts_nothing(self):
        open(os.path.join(self.d, "warmspaces.js"), "w").write("x=" + json.dumps({"items": []}) + ";")
        open(os.path.join(self.d, "logs", "discovery_today_warmspaces.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": [], "queued": {}})
        )
        FR.deliver("warmspaces", root=self.d, ref=None, run_started=RUN_START, post_fn=self.post)
        self.assertEqual(self.posted, [])

    def test_new_place_listed(self):
        open(os.path.join(self.d, "warmspaces.js"), "w").write(
            "x=" + json.dumps({"items": [{"id": "ws-old", "name": "Old"}]}) + ";"
        )
        open(os.path.join(self.d, "logs", "discovery_today_warmspaces.json"), "w").write(
            json.dumps(
                {
                    "day": "2026-10-30",
                    "added": [{"id": "ws-new", "name": "New Warm Hub", "postcode": "AB1 2CD"}],
                    "queued": {},
                }
            )
        )
        FR.deliver("warmspaces", root=self.d, ref=None, run_started=RUN_START, post_fn=self.post)
        self.assertEqual(len(self.posted), 1)
        self.assertIn("New Warm Hub", self.posted[0][2])
        self.assertIn("AB1 2CD", self.posted[0][2])

    def test_already_published_not_listed(self):
        open(os.path.join(self.d, "warmspaces.js"), "w").write(
            "x=" + json.dumps({"items": [{"id": "ws-dup", "name": "Already there"}]}) + ";"
        )
        open(os.path.join(self.d, "logs", "discovery_today_warmspaces.json"), "w").write(
            json.dumps(
                {
                    "day": "2026-10-30",
                    "added": [{"id": "ws-dup", "name": "Already there", "postcode": "X1 1XX"}],
                    "queued": {},
                }
            )
        )
        self.assertIsNone(FR.build_report("warmspaces", root=self.d, ref=None, run_started=RUN_START))

    def test_output_cap(self):
        rows = [{"id": "x-%d" % i, "name": "Place %d" % i, "postcode": "P%d" % i} for i in range(40)]
        open(os.path.join(self.d, "logs", "discovery_today_warmspaces.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": rows, "queued": {}})
        )
        open(os.path.join(self.d, "warmspaces.js"), "w").write("x=" + json.dumps({"items": []}) + ";")
        text = FR.build_report("warmspaces", root=self.d, ref=None, run_started=RUN_START)
        self.assertIn("and 10 more", text)
        self.assertEqual(text.count("- Place"), FR.LINE_CAP)

    def test_emergency_swep_change_lists_section(self):
        open(os.path.join(self.d, "logs", "discovery_today_shelters.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": [], "queued": {}})
        )
        open(os.path.join(self.d, "logs", "swep_status.json"), "w").write(
            json.dumps(
                {
                    "run": "2026-10-30",
                    "changes": [
                        {
                            "council": "Swindon Borough Council",
                            "url": "https://example.gov/swep",
                            "from": "not active",
                            "to": "active",
                            "quote": "SWEP is now active for rough sleepers",
                        }
                    ],
                }
            )
        )
        text = FR.build_report("shelters", root=self.d, ref=None, run_started=RUN_START)
        self.assertIn("INCIDENT REST CENTRES AND SWEP", text)
        self.assertIn("Swindon Borough Council", text)
        self.assertIn("SWEP is now active", text)

    def test_emergency_preview_held_alone_does_not_skip_nothing_new_rule_without_other_news(self):
        """Held emergency preview items count as news; no 'live on site' listing."""
        open(os.path.join(self.d, "data.full.js"), "w").write("x=" + json.dumps({"items": []}) + ";")
        open(os.path.join(self.d, "logs", "discovery_today_foodbanks.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": [], "queued": {}})
        )
        open(os.path.join(self.d, "reports", "emergency_preview.json"), "w").write(
            json.dumps({"held": [{"name": "Town Hall rest centre", "tell_dean": "needs OK first"}]})
        )
        text = FR.build_report("foodbanks", root=self.d, ref=None, run_started=RUN_START)
        self.assertIn("Town Hall rest centre", text)
        self.assertNotIn("live on the site", text.lower())
        self.assertNotIn("went live", text.lower())

    def test_address_held_listed(self):
        open(os.path.join(self.d, "data.full.js"), "w").write("x=" + json.dumps({"items": []}) + ";")
        open(os.path.join(self.d, "logs", "discovery_today_foodbanks.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": [], "queued": {}})
        )
        tag = "address review foodbanks"
        block = (
            "<!-- %s -->\n## Address and pin mismatches (not applied)\n\n"
            "- address mismatch, held for Dean | hull | address | via refresh | stored Old Street | proposed New Street | unchanged | Hull Foodbank\n"
            "<!-- /%s -->\n"
            % (tag, tag)
        )
        open(os.path.join(self.d, "reports", "pending_dean.md"), "w").write("# Pending\n\n" + block)
        text = FR.build_report("foodbanks", root=self.d, ref=None, run_started=RUN_START)
        self.assertIn("Address or pin held", text)
        self.assertIn("Hull Foodbank", text)

    def test_swep_unchanged_since_baseline_posts_nothing(self):
        payload = {
            "run": "2026-10-30",
            "changes": [
                {
                    "council": "X Council",
                    "url": "https://x.gov",
                    "from": "not active",
                    "to": "active",
                    "quote": "active now",
                }
            ],
        }
        p = os.path.join(self.d, "logs", "swep_status.json")
        open(p, "w").write(json.dumps(payload))
        open(os.path.join(self.d, "logs", "discovery_today_shelters.json"), "w").write(
            json.dumps({"day": "2026-10-30", "added": [], "queued": {}})
        )
        import subprocess

        subprocess.run(["git", "init", "-q"], cwd=self.d, check=True)
        subprocess.run(["git", "-C", self.d, "config", "user.email", "t@t.com"], check=True)
        subprocess.run(["git", "-C", self.d, "config", "user.name", "t"], check=True)
        subprocess.run(["git", "add", "logs/swep_status.json"], cwd=self.d, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.d, check=True)
        ref = subprocess.check_output(["git", "-C", self.d, "rev-parse", "HEAD"], text=True).strip()
        self.assertIsNone(FR.build_report("shelters", root=self.d, ref=ref, run_started=RUN_START))


if __name__ == "__main__":
    unittest.main()
