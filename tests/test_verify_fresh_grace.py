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
