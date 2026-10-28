"""Refresh 28 Oct 21:35 (run 40771267202) refused to publish: carry_forward.py (Dean, 28 Oct) kept two warm spaces that
were not re-confirmed (ww-69177710 left the feed, ww-65441920's site now redirects) with 'call before you go', and
verify_fresh.py had no rule for them. A carried venue passes only if it is labelled, in THIS run's carry-forward log,
was published before with the same fetched_at, and its source did not say closed this run. Everything else still fails."""
import datetime, json, os, shutil, subprocess, sys, tempfile, unittest
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, S)
import carry_forward as C

RUN = datetime.date.today().isoformat()
def iso(h): return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=h)).replace(microsecond=0).isoformat()
OLD = iso(24)
KINGS = {"id": "ww-65441920", "name": "The King's Church Halifax", "postcode": "HX1 2TS", "lat": 53.72, "lng": -1.87, "hours": {"Mon": "08:30 - 14:30"},
         "website": "https://kingschurchhx.org.uk/", "last_verified": OLD[:10], "tier": "unverified", "fetched_at": OLD, "stale": False}
LIGHT = {"id": "ww-69177710", "name": "Community Support Warm Welcome", "postcode": "HA1 3LL", "lat": 51.57, "lng": -0.34, "hours": {"Fri": "12:30 - 15:00"},
         "last_verified": OLD[:10], "tier": "unverified", "fetched_at": OLD, "stale": False}
HUB = {"id": "ww-1", "name": "Confirmed Hub", "postcode": "N3 1TR", "lat": 51.6, "lng": -0.19, "hours": {}, "last_verified": RUN, "tier": "unverified", "stale": False}
PENDING = [{"id": KINGS["id"], "recheck": {"url": "https://kingschurchhx.org.uk/", "final_url": "https://cornerstonechurchhalifax.co.uk/", "fetched_at": iso(0), "http": 200}}]

def js(var, items): return "var %s=%s;\n" % (var, json.dumps({"items": items}))

class CarryForwardGuard(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(self.d + "/logs")
        self.env = dict(os.environ, REFRESH_RUN_ID="run-1"); self.env.pop("GITHUB_RUN_ID", None)
        g = lambda *a: subprocess.run(["git", *a], cwd=self.d, check=True, capture_output=True)
        g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        open(self.d + "/warmspaces.js", "w").write(js("WARMSPACES", [KINGS, LIGHT, dict(HUB, fetched_at=OLD)]))
        open(self.d + "/shelters.js", "w").write(js("SHELTERS", [dict(HUB, fetched_at=OLD)]))
        g("add", "-A"); g("commit", "-qm", "published")
        self.now = iso(0)
        self.rc = {"_run": {"fetched_at": self.now}, HUB["id"]: {"ok": True, "fetched_at": self.now},
                   KINGS["id"]: {"ok": False, "http": 200, "reason": "source URL now redirects to a different site (cornerstonechurchhalifax.co.uk)", "fetched_at": self.now}}

    def tearDown(self): shutil.rmtree(self.d)

    def build(self, prev=None, log_run_id="run-1"):
        """What build_warmspaces.py does: this run confirms only HUB; carry_forward keeps the rest, labelled and logged."""
        items, carried, nc = C.carry_items(prev or [KINGS, LIGHT, HUB], [dict(HUB, fetched_at=self.now)], [], RUN, allowed=set(), pending=PENDING)
        os.environ["REFRESH_RUN_ID"] = log_run_id
        try: C.write_log(carried, RUN, root=self.d, not_carried=nc)
        finally: os.environ.pop("REFRESH_RUN_ID", None)
        return items

    def verify(self, items, layer="warmspaces", rc=None):
        out, var = {"warmspaces": ("warmspaces.js", "WARMSPACES"), "shelters": ("shelters.js", "SHELTERS")}[layer]
        open(os.path.join(self.d, out), "w").write(js(var, items))
        json.dump(rc or self.rc, open(os.path.join(self.d, "logs", layer + "_recheck.json"), "w"))
        p = subprocess.run([sys.executable, S + "/verify_fresh.py", layer], cwd=self.d, env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_failed_run_shape_now_publishes(self):
        items = self.build()
        self.assertEqual({x["id"] for x in items if x.get("carried_forward")}, {KINGS["id"], LIGHT["id"]})
        code, out = self.verify(items)
        self.assertEqual(code, 0, out)
        self.assertNotIn("website", next(x for x in items if x["id"] == KINGS["id"]))  # redirect: link dropped, as carry_forward promises

    def test_unlabelled_unconfirmed_still_refused(self):
        items = [dict(x) for x in self.build()]
        next(x for x in items if x["id"] == LIGHT["id"]).pop("call_check")
        code, out = self.verify(items)
        self.assertEqual(code, 1); self.assertIn(LIGHT["id"] + " not confirmed this run", out)
        code, out = self.verify([dict(HUB, fetched_at=self.now), dict(LIGHT)])
        self.assertEqual(code, 1); self.assertIn(LIGHT["id"] + " not confirmed this run", out)

    def test_not_in_this_runs_log_refused(self):
        items = self.build(log_run_id="run-0")
        code, out = self.verify(items)
        self.assertEqual(code, 1); self.assertIn("not in this run's carry-forward log", out)
        os.remove(os.path.join(self.d, "logs", "warmspaces_carry_forward.json"))
        self.assertEqual(self.verify(items)[0], 1)

    def test_never_published_refused(self):
        new = dict(LIGHT, id="ww-999", name="Invented Hub")
        items = self.build(prev=[KINGS, LIGHT, HUB, new])
        code, out = self.verify(items)
        self.assertEqual(code, 1); self.assertIn("ww-999 carried but was not published before", out)

    def test_fresher_fetched_at_refused(self):
        items = [dict(x, fetched_at=self.now) if x["id"] == LIGHT["id"] else x for x in self.build()]
        code, out = self.verify(items)
        self.assertEqual(code, 1); self.assertIn("fetched_at differs from the published copy", out)

    def test_source_says_closed_refused(self):
        rc = dict(self.rc); rc[KINGS["id"]] = {"ok": False, "http": 200, "reason": "source now says closed/ended", "fetched_at": self.now}
        code, out = self.verify(self.build(), rc=rc)
        self.assertEqual(code, 1); self.assertIn("source says closed/ended", out)

    def test_shelters_have_no_carry_exception(self):
        carried = C.label(dict(LIGHT, id=HUB["id"], fetched_at=OLD), RUN)
        code, out = self.verify([carried], layer="shelters", rc={"_run": {"fetched_at": self.now}})
        self.assertEqual(code, 1); self.assertIn("not confirmed this run", out)

if __name__ == "__main__":
    unittest.main()
