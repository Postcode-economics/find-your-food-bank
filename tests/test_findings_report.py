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


if __name__ == "__main__":
    unittest.main()
