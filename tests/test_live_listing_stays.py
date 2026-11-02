"""A live listing stays when its page, link or feed row cannot be read (2 Nov 2026).

Shelters, food banks and warm spaces: blocked, 404, timeout, a missing read and an old grace do not remove a place
that is already on the map. It is removed only when its own source says it has closed. A place that was never
published, and whose read failed, is held for this run. One place does not fail the run. An empty file still does.
"""
import datetime, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, S)
import common, fb_recheck, carry_forward

NOW = datetime.datetime(2026, 11, 2, 12, tzinfo=datetime.timezone.utc)
V = {"p": {"evidence_url": "https://example.org/p", "quote": "Open", "verified_on": "2020-01-01"}}

def row(i="p"):
    return {"id": i, "name": i, "source": "OpenStreetMap", "fetched_at": "2020-01-01T00:00:00+00:00", "phone": "0161 000 0000", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}

class Gate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d); os.makedirs("logs"); self.addCleanup(self._back)
    def _back(self):
        os.chdir(self.cwd); shutil.rmtree(self.d, True)
    def go(self, pending, rc, prev, fresh=None):
        fresh = fresh or [row()]
        with mock.patch("recheck.recheck_all", return_value=rc):
            pub, _, _ = common.verification_gate(fresh, prev, V, "2026-11-02", pending, now=NOW)
        return pub
    def test_shelter_published_404_stays_and_a_new_one_is_held(self):
        live = {"items": [row("old")]}
        rc = {"old": {"ok": False, "http": 404, "reason": "source unreachable this run (HTTP 404)"},
              "new": {"ok": False, "http": "timeout", "reason": "timeout"}}
        pub = self.go("logs/shelters_pending.json", rc, live, [row("old"), row("new")])
        self.assertEqual([x["id"] for x in pub], ["old"])
        self.assertTrue(pub[0]["kept_fetch_blocked"])
        self.assertEqual(pub[0]["fetched_at"], "2020-01-01T00:00:00+00:00")
        self.assertIn("new", open("reports/manual_review.md").read())
        self.assertNotIn("old", open("reports/manual_review.md").read())
    def test_warm_space_published_blocked_stays_past_any_grace(self):
        live = {"items": [row("ws")]}
        pub = self.go("logs/warmspaces_pending.json", {"ws": {"ok": False, "http": 403, "reason": "source unreachable this run (HTTP 403)"}}, live, [row("ws")])
        self.assertEqual([x["id"] for x in pub], ["ws"])
        self.assertTrue(pub[0]["kept_fetch_blocked"])
    def test_closed_source_is_left_off_every_layer(self):
        for pending in ("logs/shelters_pending.json", "logs/warmspaces_pending.json"):
            live = {"items": [row()]}
            pub = self.go(pending, {"p": {"ok": False, "http": 200, "reason": "source now says closed/ended"}}, live)
            self.assertEqual(pub, [], pending)
            self.assertIn("source now says closed", open("reports/manual_review.md").read())
    def test_unseen_for_years_is_not_closed(self):
        items, closed = common.merge_lifecycle({"items": [{"id": "a", "name": "A", "last_verified": "2020-01-01"}], "recently_closed": []}, [], "2026-11-02")
        self.assertEqual([x["id"] for x in items], ["a"]); self.assertEqual(closed, [])
        items, closed = common.merge_lifecycle({"items": [{"id": "a", "name": "A", "last_verified": "2026-11-01", "flag_closed": True}], "recently_closed": []}, [], "2026-11-02")
        self.assertEqual(items, []); self.assertEqual(closed[0]["id"], "a")

class Food(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(self.d + "/logs"); self.addCleanup(shutil.rmtree, self.d, True)
    def item(self, **k):
        x = dict(id="acme", type="foodbank", name="Acme Foodbank", foodbank="Acme Foodbank", network="", address="1 High St", postcode="AB1 2CD",
                 lat=52.0, lng=-1.0, phone="01234 567890", website="https://acme.org.uk/", givefood="https://www.givefood.org.uk/needs/at/acme/", opening_times=None, fetched_at="2020-01-01T00:00:00+00:00")
        x.update(k); return x
    def gate(self, items, records=None, fetcher=None, published=None):
        meta = {"foodbanks": {"http": 200, "final_url": "https://www.givefood.org.uk/api/2/foodbanks/", "etag": "e", "last_modified": "", "sha256": "s", "fetched_at": "t"}}
        return fb_recheck.gate(items, records if records is not None else {i["id"]: {"slug": i["id"]} for i in items}, meta,
                                self.d + "/logs/foodbank_recheck.json", self.d + "/logs/foodbank_pending.json",
                                fetcher=fetcher or (lambda u: {"http": 404, "final_url": u, "text": "", "sha256": "x"}), per_run=0, run_key="k", published_ids=published)
    def test_published_missing_page_stays_and_a_new_one_is_held(self):
        live = self.item(directory="IFAN", givefood="", own_site_check={"http": 404, "final_url": "https://acme.org.uk/"})
        new = self.item(id="new", name="New Bank", foodbank="New Bank")
        pub, om = self.gate([live, new], records={"acme": {"slug": "acme"}}, published={"acme"})
        self.assertEqual([x["id"] for x in pub], ["acme"])
        self.assertTrue(pub[0]["kept_fetch_blocked"]); self.assertEqual(pub[0]["fetched_at"], "2020-01-01T00:00:00+00:00")
        self.assertEqual(om[0]["id"], "new")
        self.assertIn("new", open(self.d + "/reports/manual_review.md").read())
    def test_published_page_that_does_not_name_it_stays(self):
        pub, om = fb_recheck.gate([self.item()], {"acme": {"slug": "acme"}}, {"foodbanks": {"http": 200, "final_url": "https://www.givefood.org.uk/api/2/foodbanks/", "etag": "e", "last_modified": "", "sha256": "s", "fetched_at": "t"}},
                                   self.d + "/logs/foodbank_recheck.json", self.d + "/logs/foodbank_pending.json",
                                   fetcher=lambda u: {"http": 200, "final_url": "https://www.givefood.org.uk/needs/at/acme/", "text": "some other charity", "sha256": "x"},
                                   per_run=5, run_key="k", published_ids={"acme"})
        self.assertEqual([x["id"] for x in pub], ["acme"]); self.assertEqual(om, [])
    def test_api_failure_still_stops_the_run(self):
        meta = {"foodbanks": {"http": 503, "final_url": "https://www.givefood.org.uk/api/2/foodbanks/", "etag": "", "last_modified": "", "sha256": "", "fetched_at": "t"}}
        with self.assertRaises(RuntimeError):
            fb_recheck.gate([self.item()], {"acme": {}}, meta, self.d + "/logs/r.json", self.d + "/logs/p.json", published_ids={"acme"})

class Carry(unittest.TestCase):
    def test_missing_feed_row_stays_and_a_stated_end_does_not(self):
        v = {"id": "ww", "name": "Hall", "verified_on": "2026-10-01", "last_verified": "2026-10-01"}
        items, _, nc = carry_forward.carry_items([v], [], [], "2027-06-01", allowed=set(), valid_until=carry_forward.season_end)
        self.assertEqual([x["id"] for x in items], ["ww"]); self.assertEqual(nc, [])
        ended = dict(v, scheme_end="2026-12-01")
        items, _, nc = carry_forward.carry_items([ended], [], [], "2027-01-01", allowed=set())
        self.assertEqual(items, []); self.assertEqual(nc[0]["why"], "season_ended")
        closed = [dict(v, id="c")]
        pend = [{"id": "c", "reason": "omitted this run: source now says closed/ended"}]
        items, _, nc = carry_forward.carry_items(closed, [], [], "2026-11-02", allowed=set(), pending=pend)
        self.assertEqual(items, []); self.assertEqual(nc[0]["why"], "closed")

class Fresh(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(self.d + "/logs"); self.addCleanup(shutil.rmtree, self.d, True)
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.d, capture_output=True, check=True)
        g("init", "-q"); self.git = g
    def file(self, name, var, items):
        return "window.%s = %s;" % (var, json.dumps({"items": items}))
    def go(self, layer, name, var, published, current, logname, rows):
        self.git("add", "-A") if False else None
        open(self.d + "/" + name, "w").write(self.file(name, var, published))
        self.git("add", name); self.git("commit", "-qm", name)
        open(self.d + "/" + name, "w").write(self.file(name, var, current))
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        body = {"_run": {"fetched_at": now}}; body.update(rows)
        json.dump(body, open(self.d + "/logs/" + logname, "w"))
        p = subprocess.run([sys.executable, S + "/verify_fresh.py", layer], cwd=self.d, capture_output=True, text=True)
        text = open(self.d + "/" + name).read()
        return p, text
    def test_each_layer_drops_only_the_failed_new_place(self):
        now_id = {"id": "live", "fetched_at": "2020-01-01T00:00:00+00:00"}
        new = {"id": "new", "fetched_at": "2020-01-01T00:00:00+00:00"}
        for layer, name, var, log in (("shelters", "shelters.js", "SHELTERS", "shelters_recheck.json"),
                                      ("warmspaces", "warmspaces.js", "WARMSPACES", "warmspaces_recheck.json"),
                                      ("foodbanks", "data.full.js", "FB_DATA", "foodbank_recheck.json")):
            p, text = self.go(layer, name, var, [now_id], [now_id, new], log, {"live": {"ok": False, "http": 404, "reason": "source unreachable this run (HTTP 404)"}, "new": {"ok": False, "http": 404}})
            self.assertEqual(p.returncode, 0, layer + p.stdout + p.stderr)
            self.assertIn("live", text); self.assertNotIn('"new"', text)
    def test_empty_after_a_closure_still_refuses(self):
        item = {"id": "only", "fetched_at": "2020-01-01T00:00:00+00:00"}
        p, text = self.go("shelters", "shelters.js", "SHELTERS", [item], [item], "shelters_recheck.json", {"only": {"ok": False, "http": 200, "reason": "source now says closed/ended"}})
        self.assertEqual(p.returncode, 1); self.assertIn("empty after holding", p.stdout); self.assertIn("only", text)

if __name__ == "__main__":
    unittest.main()
