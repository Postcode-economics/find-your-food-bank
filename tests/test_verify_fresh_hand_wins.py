"""verify_fresh ran after the build and put the published address/hours back on every card, undoing
hand-checked manual values (practice refresh 41865536193). Hand values must survive it; feed-only changes must not."""
import json, os, shutil, subprocess, sys, tempfile, unittest, datetime
ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "scripts")

def js(items):
    return "var SHELTERS=" + json.dumps({"updated": "x", "items": items}, ensure_ascii=False, separators=(",", ":")) + ";\n"

class VerifyFreshHandWins(unittest.TestCase):
    def run_vf(self, published, built, manual, reads=None):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        shutil.copytree(SRC, os.path.join(d, "scripts"))
        for sub in ("overrides", "logs"): os.makedirs(os.path.join(d, sub))
        json.dump(manual, open(os.path.join(d, "overrides", "shelters_manual.json"), "w"))
        json.dump({}, open(os.path.join(d, "overrides", "shelters_verified.json"), "w"))
        open(os.path.join(d, "shelters.js"), "w").write(js(published))
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        e = {"cwd": d, "capture_output": True, "text": True, "env": env, "check": True}
        subprocess.run(["git", "init", "-q"], **e); subprocess.run(["git", "add", "-A"], **e)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-qm", "pub"], **e)
        # the published copy must be readable at HEAD, or verify_fresh has nothing to protect and this test proves nothing
        self.assertIn('"id":"b"', subprocess.run(["git", "show", "HEAD:shelters.js"], **e).stdout)
        open(os.path.join(d, "shelters.js"), "w").write(js(built))
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log = {"_run": {"fetched_at": now}}
        for b in built: log[b["id"]] = dict({"ok": True, "fetched_at": b.get("fetched_at")}, **((reads or {}).get(b["id"]) or {}))
        json.dump(log, open(os.path.join(d, "logs", "shelters_recheck.json"), "w"))
        vf = subprocess.run([sys.executable, "scripts/verify_fresh.py", "shelters"], cwd=d, capture_output=True, text=True, env=env)
        self.vf_out = vf.stdout + vf.stderr
        self.assertEqual(vf.returncode, 0, self.vf_out)  # verify_fresh must actually run, not stop early
        t = open(os.path.join(d, "shelters.js")).read()
        return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}

    def test_hand_address_and_hours_survive_and_feed_change_does_not(self):
        # a = hand values; b = read OK, build already decided (verify_fresh must not freeze it, rule 50);
        # c = read FAILED: the published copy comes back, except a hand value
        pub = [{"id": "a", "name": "A", "address": "1 Rd, Manchester", "hours": "", "phone": "0161 000 0000", "postcode": "M1 1AA", "fetched_at": "t0"},
               {"id": "b", "name": "B", "address": "2 Rd", "hours": "", "phone": "0161 111 1111", "postcode": "M1 1AB", "fetched_at": "t0"},
               {"id": "c", "name": "C", "address": "3 Rd", "hours": "", "phone": "0161 222 2222", "postcode": "M1 1AC", "fetched_at": "t0"},
               {"id": "d", "name": "D", "address": "4 Rd", "hours": "", "phone": "0161 333 3333", "postcode": "M1 1AD", "fetched_at": "t0"}]
        built = [dict(pub[0], address="1 Rd, Hulme", hours="Staffed 24/7", fetched_at="t1"),
                 dict(pub[1], address="2 Moved Rd", hours="Mo-Fr 09:00-17:00", fetched_at="t1"),
                 dict(pub[2], address="9 Feed Rd", hours="Mo-Fr 09:00-17:00", phone="0800 000 000", postcode="ZZ9 9ZZ", fetched_at="t1"),
                 dict(pub[3], address="1 Rd, Hand", fetched_at="t1")]
        out = self.run_vf(pub, built, [{"id": "a", "address": "1 Rd, Hulme", "hours": "Staffed 24/7"}, {"id": "d", "address": "1 Rd, Hand"}],
                          reads={"c": {"ok": False}, "d": {"ok": False}})
        self.assertEqual(out["a"]["address"], "1 Rd, Hulme")
        self.assertEqual(out["a"]["hours"], "Staffed 24/7")
        self.assertEqual(out["a"]["phone"], "0161 000 0000")
        self.assertEqual(out["b"]["address"], "2 Moved Rd", getattr(self, "vf_out", ""))
        self.assertEqual(out["b"]["hours"], "Mo-Fr 09:00-17:00")
        for f in ("address", "hours", "phone", "postcode", "fetched_at"):
            self.assertEqual(out["c"][f], pub[2][f], f)
        self.assertEqual(out["d"]["address"], "1 Rd, Hand")
        self.assertEqual(out["d"]["phone"], pub[3]["phone"])

    def test_confirmed_hours_change_survives(self):
        # rules 33/48: hours the times gate auto-applied stay, on an OK read and on a failed read
        pub = [{"id": "e", "name": "E", "address": "5 Rd", "hours": "Mo 10:00-12:00", "phone": "0161 444 4444", "postcode": "M1 1AE", "fetched_at": "t0"},
               {"id": "f", "name": "F", "address": "6 Rd", "hours": "Mo 10:00-12:00", "phone": "0161 555 5555", "postcode": "M1 1AF", "fetched_at": "t0"}]
        built = [dict(pub[0], hours="Mo-Fr 09:00-17:00", fetched_at="t1"), dict(pub[1], hours="Tu 09:00-11:00", fetched_at="t1")]
        out = self.run_vf(pub, built, [], reads={"e": {"auto_applied": True}, "f": {"ok": False, "auto_applied": True}})
        self.assertEqual(out["e"]["hours"], "Mo-Fr 09:00-17:00", getattr(self, "vf_out", ""))
        self.assertEqual(out["f"]["hours"], "Tu 09:00-11:00")
        self.assertEqual(out["f"]["address"], "6 Rd")

if __name__ == "__main__":
    unittest.main()
