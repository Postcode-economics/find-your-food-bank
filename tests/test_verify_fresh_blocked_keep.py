"""Hand-checked rows kept through a blocked fetch (common.verification_gate, MANUAL_BLOCK_DAYS) pass verify_fresh only when
blocked, hand-checked within 14 days, already published, and unchanged against the published copy (2 Nov 2026)."""
import os, sys, json, tempfile, subprocess, unittest, datetime
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
def day(d): return (datetime.date.today() - datetime.timedelta(days=d)).isoformat()
def row(d=2, **kw):
    x = {"id": "man-a", "grace": True, "kept_fetch_blocked": True, "source": "Manual (verified from source pages)", "checked_on": day(d),
         "fetched_at": day(d) + "T00:00:00+00:00", "phone": "0161 000 0000", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}
    x.update(kw); return x
def js(items): return "window.SHELTERS = " + json.dumps({"items": items}) + ";"
class Blocked(unittest.TestCase):
    def go(self, item, r, published=None):
        d = tempfile.mkdtemp(); os.makedirs(d + "/logs")
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d, capture_output=True, check=True)
        g("init", "-q")
        pub = dict(item); pub.pop("grace", None); pub.pop("kept_fetch_blocked", None)
        open(d + "/shelters.js", "w").write(js([pub] if published is None else published))
        g("add", "."); g("commit", "-qm", "published")
        open(d + "/shelters.js", "w").write(js([item]))
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        json.dump({"_run": {"fetched_at": now}, item["id"]: r}, open(d + "/logs/shelters_recheck.json", "w"))
        p = subprocess.run([sys.executable, S + "/verify_fresh.py", "shelters"], cwd=d, capture_output=True, text=True)
        return p.returncode
    def test_blocked_2_days_passes(self): self.assertEqual(self.go(row(2), {"ok": False, "http": 403}), 0)
    def test_timeout_passes(self): self.assertEqual(self.go(row(2), {"ok": False, "http": "timeout"}), 0)
    def test_15_days_fails(self): self.assertEqual(self.go(row(15), {"ok": False, "http": 403}), 1)
    def test_page_loaded_but_closed_fails(self): self.assertEqual(self.go(row(2), {"ok": False, "http": 200, "reason": "source now says closed/ended"}), 1)
    def test_not_previously_published_fails(self): self.assertEqual(self.go(row(2), {"ok": False, "http": 403}, published=[]), 1)
    def test_changed_phone_fails(self):
        old = row(2); old.pop("grace"); old.pop("kept_fetch_blocked"); old["phone"] = "0161 999 9999"
        self.assertEqual(self.go(row(2), {"ok": False, "http": 403}, published=[old]), 1)
    def test_changed_fetched_at_fails(self):
        old = row(2); old.pop("grace"); old.pop("kept_fetch_blocked"); old["fetched_at"] = day(1) + "T00:00:00+00:00"
        self.assertEqual(self.go(row(2), {"ok": False, "http": 403}, published=[old]), 1)
    def test_non_manual_with_flag_fails(self): self.assertEqual(self.go(row(2, source="OpenStreetMap"), {"ok": False, "http": 403}), 1)
    def test_48h_grace_without_flag_still_old_rule(self):
        x = row(5); x.pop("kept_fetch_blocked")
        self.assertEqual(self.go(x, {"ok": False, "http": 403}), 1)
if __name__ == "__main__": unittest.main()
