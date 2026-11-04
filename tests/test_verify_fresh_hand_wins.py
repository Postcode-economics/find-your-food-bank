"""verify_fresh ran after the build and put the published address/hours back on every card, undoing
hand-checked manual values (practice refresh 41865536193). Hand values must survive it; feed-only changes must not."""
import json, os, shutil, subprocess, sys, tempfile, unittest, datetime
ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "scripts")

def js(items):
    return "var SHELTERS=" + json.dumps({"updated": "x", "items": items}, ensure_ascii=False, separators=(",", ":")) + ";\n"

class VerifyFreshHandWins(unittest.TestCase):
    def run_vf(self, published, built, manual):
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
        for b in built: log[b["id"]] = {"ok": True, "fetched_at": b.get("fetched_at")}
        json.dump(log, open(os.path.join(d, "logs", "shelters_log.json"), "w"))
        vf = subprocess.run([sys.executable, "scripts/verify_fresh.py", "shelters"], cwd=d, capture_output=True, text=True, env=env)
        self.vf_out = vf.stdout + vf.stderr
        t = open(os.path.join(d, "shelters.js")).read()
        return {i["id"]: i for i in json.loads(t[t.index("{"):t.rindex("}") + 1])["items"]}

    def test_hand_address_and_hours_survive_and_feed_change_does_not(self):
        pub = [{"id": "a", "name": "A", "address": "1 Rd, Manchester", "hours": "", "phone": "0161 000 0000", "postcode": "M1 1AA", "fetched_at": "t0"},
               {"id": "b", "name": "B", "address": "2 Rd", "hours": "", "phone": "0161 111 1111", "postcode": "M1 1AB", "fetched_at": "t0"}]
        built = [dict(pub[0], address="1 Rd, Hulme", hours="Staffed 24/7", fetched_at="t1"),
                 dict(pub[1], address="9 Feed Rd", hours="Mo-Fr 09:00-17:00", fetched_at="t1")]
        out = self.run_vf(pub, built, [{"id": "a", "address": "1 Rd, Hulme", "hours": "Staffed 24/7"}])
        self.assertEqual(out["a"]["address"], "1 Rd, Hulme")
        self.assertEqual(out["a"]["hours"], "Staffed 24/7")
        self.assertEqual(out["a"]["phone"], "0161 000 0000")
        self.assertEqual(out["b"]["address"], "2 Rd", getattr(self, "vf_out", ""))
        self.assertEqual(out["b"]["hours"], "")

if __name__ == "__main__":
    unittest.main()
