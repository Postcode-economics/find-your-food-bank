"""Dean 1 Nov 2026: a hand-checked shelters_manual row (checked_on within 14 days) stays published when its source
fetch is blocked (403/429/5xx/timeout); never when the page loads and says closed / no longer names the place."""
import os, sys, json, tempfile, unittest, datetime
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common

NOW = datetime.datetime(2026, 11, 1, 12, 0, tzinfo=datetime.timezone.utc)
V = {"m1": {"evidence_url": "https://example.org/", "quote": "Hostel", "verified_on": "2026-10-31"}}

class ManualBlocked(unittest.TestCase):
    def run_gate(self, rc, checked_on="2026-10-31", source="Manual (verified from source pages)"):
        d = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(d)
        try:
            os.makedirs("logs")
            row = {"id": "m1", "name": "Test Hostel", "source": source, "checked_on": checked_on}
            with mock.patch("recheck.recheck_all", return_value={"m1": rc}):
                pub, _, _ = common.verification_gate([row], None, V, "2026-11-01", "logs/sh_pending.json", now=NOW)
            return pub, open("reports/sh_grace.md").read(), json.load(open("logs/sh_pending.json"))
        finally: os.chdir(cwd)
    def test_blocked_codes_kept_and_logged(self):
        for h in (403, 429, 500, 503, "error", "timeout"):
            pub, rep, pend = self.run_gate({"ok": False, "http": h, "reason": "source unreachable this run (HTTP %s)" % h})
            self.assertEqual([x["id"] for x in pub], ["m1"], h); self.assertIn("kept, fetch blocked", rep); self.assertEqual(pend, [])
            self.assertTrue(any(g.get("kept_fetch_blocked") for g in common.verification_gate.graced))
    def test_dropped_after_14_days(self):
        pub, _, pend = self.run_gate({"ok": False, "http": 403, "reason": "x"}, checked_on="2026-10-17")
        self.assertEqual(pub, []); self.assertEqual(len(pend), 1)
    def test_kept_at_14_days(self):
        pub, _, _ = self.run_gate({"ok": False, "http": 403, "reason": "x"}, checked_on="2026-10-18")
        self.assertEqual(len(pub), 1)
    def test_loaded_closed_never_kept(self):
        for r in ("source now says closed/ended", "source no longer names this place"):
            pub, _, _ = self.run_gate({"ok": False, "http": 200, "reason": r}); self.assertEqual(pub, [], r)
    def test_404_not_kept(self):
        pub, _, _ = self.run_gate({"ok": False, "http": 404, "reason": "x"}); self.assertEqual(pub, [])
    def test_non_manual_not_kept(self):
        pub, _, _ = self.run_gate({"ok": False, "http": 403, "reason": "x"}, source="Homeless Link Find help"); self.assertEqual(pub, [])

if __name__ == "__main__": unittest.main()
