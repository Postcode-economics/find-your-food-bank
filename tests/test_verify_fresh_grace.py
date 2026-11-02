import os, sys, json, tempfile, subprocess, unittest, datetime
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
def iso(h): return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=h)).replace(microsecond=0).isoformat()
class VF(unittest.TestCase):
    def go(self, item, r):
        d = tempfile.mkdtemp(); os.makedirs(d + "/logs")
        open(d + "/shelters.js", "w").write("window.SHELTERS = " + json.dumps({"items": [item]}) + ";")
        json.dump({"_run": {"fetched_at": iso(0)}, item["id"]: r}, open(d + "/logs/shelters_recheck.json", "w"))
        return subprocess.run([sys.executable, S + "/verify_fresh.py", "shelters"], cwd=d, capture_output=True, text=True).returncode
    def test_grace_ok(self): self.assertEqual(self.go({"id": "a", "grace": True, "fetched_at": iso(20)}, {"ok": False, "http": 429}), 0)
    def test_grace_too_old(self): self.assertEqual(self.go({"id": "a", "grace": True, "fetched_at": iso(50)}, {"ok": False, "http": 429}), 1)
    def test_grace_content_fail(self): self.assertEqual(self.go({"id": "a", "grace": True, "fetched_at": iso(2)}, {"ok": False, "http": 200, "reason": "source now says closed/ended"}), 1)
    def test_plain_unconfirmed(self): self.assertEqual(self.go({"id": "a", "fetched_at": iso(0)}, {"ok": False, "http": 429}), 1)
    def day(self, d): return (datetime.date.today() - datetime.timedelta(days=d)).isoformat()
    def man(self, d): return {"id": "man-a", "grace": True, "source": "Manual (verified from source pages)", "checked_on": self.day(d), "fetched_at": self.day(d) + "T00:00:00+00:00"}
    # Dean 1 Nov 2026: hand-checked manual rows survive a blocked fetch for 14 days (same rule as verification_gate)
    def test_manual_blocked_within_14_days_ok(self): self.assertEqual(self.go(self.man(5), {"ok": False, "http": 403}), 0)
    def test_manual_timeout_within_14_days_ok(self): self.assertEqual(self.go(self.man(5), {"ok": False, "http": "timeout"}), 0)
    def test_manual_blocked_too_old(self): self.assertEqual(self.go(self.man(15), {"ok": False, "http": 403}), 1)
    def test_manual_page_loaded_not_kept(self): self.assertEqual(self.go(self.man(2), {"ok": False, "http": 404}), 1)
    def test_non_manual_blocked_not_kept(self):
        x = self.man(2); x["source"] = "OpenStreetMap"
        self.assertEqual(self.go(x, {"ok": False, "http": 403}), 1)
