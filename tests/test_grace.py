import os, sys, json, tempfile, unittest, datetime
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common

NOW = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=datetime.timezone.utc)
V = {"robes": {"evidence_url": "https://robes.org.uk/", "day_time_quote": "7pm", "verified_on": "2026-10-20"}}

class Grace(unittest.TestCase):
    def run_gate(self, rc, last):
        d = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(d)
        try:
            os.makedirs("logs")
            if last: json.dump({"robes": last}, open("logs/sh_last_confirmed.json", "w"))
            with mock.patch("recheck.recheck_all", return_value={"robes": rc}):
                pub, prev, n = common.verification_gate([{"id": "robes", "name": "Robes"}], None, V, "2026-10-23", "logs/sh_pending.json", now=NOW)
            return pub, json.load(open("logs/sh_last_confirmed.json")), open("reports/sh_grace.md").read()
        finally: os.chdir(cwd)
    def test_429_within_48h_kept(self):
        pub, lc, rep = self.run_gate({"ok": False, "http": 429, "reason": "source unreachable this run (HTTP 429)"}, "2026-10-22T13:00:00+00:00")
        self.assertEqual([x["id"] for x in pub], ["robes"]); self.assertTrue(pub[0]["grace"]); self.assertIn("Robes", rep)
        self.assertEqual(lc["robes"], "2026-10-22T13:00:00+00:00")
    def test_timeout_after_48h_dropped(self):
        pub, _, rep = self.run_gate({"ok": False, "http": "error", "reason": "timeout"}, "2026-10-21T10:00:00+00:00")
        self.assertEqual(pub, []); self.assertIn("None", rep)
    def test_content_failure_never_graced(self):
        pub, _, _ = self.run_gate({"ok": False, "http": 200, "reason": "source now says closed/ended"}, "2026-10-23T08:00:00+00:00")
        self.assertEqual(pub, [])
    def test_no_history_dropped(self):
        pub, _, _ = self.run_gate({"ok": False, "http": 503, "reason": "x"}, None)
        self.assertEqual(pub, [])
    def test_ok_updates_timestamp(self):
        pub, lc, _ = self.run_gate({"ok": True, "http": 200, "fetched_at": "2026-10-23T11:59:00+00:00"}, "2026-10-01T00:00:00+00:00")
        self.assertEqual(lc["robes"], "2026-10-23T11:59:00+00:00"); self.assertNotIn("grace", pub[0])
    def test_transient(self):
        for h in (429, 503, 403, "error"): self.assertTrue(common.is_transient({"ok": False, "http": h}))
        self.assertFalse(common.is_transient({"ok": False, "http": 404}))

if __name__ == "__main__": unittest.main()
