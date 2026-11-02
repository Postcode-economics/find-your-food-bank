"""A shelter whose own page is blocked is held for this run only (2 Nov 2026).

A place that was not on the map is left out of shelters.js and listed for manual review, and the rest still publishes.
A place already on the map keeps the 14-day hand-checked grace. The next run tries a held place again: the first run
its own page verifies, it is published. Nothing is frozen by id. Food banks still fail the whole publish on one bad row.
A shelters file that is empty, unreadable, or more than 20% smaller than the last published file still refuses to publish.
"""
import datetime, json, os, shutil, subprocess, sys, tempfile, unittest
from unittest import mock
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, S)
import common
import refresh_guard

NOW = datetime.datetime(2026, 11, 2, 12, 0, tzinfo=datetime.timezone.utc)
CHECKED = "2026-11-01"
V = {
    "man-new": {"evidence_url": "https://example.org/new", "quote": "Hostel", "verified_on": CHECKED},
    "man-old": {"evidence_url": "https://example.org/old", "quote": "Hostel", "verified_on": CHECKED},
}
BLOCKED = {"ok": False, "http": 403, "reason": "source unreachable this run (HTTP 403)"}
OK = {"ok": True, "http": 200, "fetched_at": "2026-11-02T12:00:00+00:00"}

def row(i, **kw):
    x = {"id": i, "name": i, "source": "Manual (verified from source pages)", "checked_on": CHECKED,
         "phone": "0161 000 0000", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}
    x.update(kw)
    return x

def js(var, items):
    return "window.%s = %s;" % (var, json.dumps({"updated": "2026-11-02", "items": items}))

class Gate(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)
        os.makedirs("logs")
        self.addCleanup(self._back)
    def _back(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d, True)
    def gate(self, rows, rc, prev=None):
        with mock.patch("recheck.recheck_all", return_value=dict(rc)):
            pub, _, _ = common.verification_gate(rows, prev, V, "2026-11-02", "logs/shelters_pending.json", now=NOW)
        return pub
    def test_new_blocked_is_held_and_the_rest_publishes(self):
        hand = "# Manual review queue (not on the map)\n\nKeep this hand-written line.\n\n<!-- AUTO-DISCOVERY QUEUE: generated, do not edit below -->\nqueue\n"
        os.makedirs("reports")
        open("reports/manual_review.md", "w").write(hand)
        pub = self.gate([row("man-new"), row("man-old")], {"man-new": BLOCKED, "man-old": OK})
        self.assertEqual([x["id"] for x in pub], ["man-old"])
        self.assertFalse(any(x.get("kept_fetch_blocked") for x in pub))
        pend = json.load(open("logs/shelters_pending.json"))
        self.assertEqual(pend[0]["id"], "man-new")
        self.assertEqual(pend[0]["reason"], "held this run: read failed, not published before")
        rep = open("reports/manual_review.md").read()
        self.assertIn("Keep this hand-written line.", rep)
        self.assertIn("<!-- AUTO-DISCOVERY QUEUE: generated, do not edit below -->", rep)
        self.assertIn("man-new", rep)
        self.assertIn("held this run: read failed, not published before", rep)
        self.assertNotIn("man-old", rep)
        grace = open("reports/shelters_grace.md").read()
        self.assertIn("man-new", grace)
        self.assertIn("Held this run (not published)", grace)
        held = json.load(open("logs/shelters_held.json"))
        self.assertEqual([h["id"] for h in held["held"]], ["man-new"])
        self.assertNotIn("man-ss-", json.dumps(held))
    def test_published_blocked_within_14_days_is_kept(self):
        # Last confirmation is older than 48 hours, so this is the 14-day blocked-fetch keep, not the short grace.
        old = row("man-old", fetched_at="2026-10-30T00:00:00+00:00")
        pub = self.gate([row("man-old")], {"man-old": BLOCKED}, prev={"items": [old]})
        self.assertEqual([x["id"] for x in pub], ["man-old"])
        self.assertTrue(pub[0].get("grace") and pub[0].get("kept_fetch_blocked"))
        self.assertEqual(pub[0]["fetched_at"], "2026-10-30T00:00:00+00:00")
        self.assertIn("kept, fetch blocked", open("reports/shelters_grace.md").read())
        rep = open("reports/manual_review.md").read()
        self.assertIn("None this run.", rep)
        self.assertNotIn("man-old", rep)
    def test_held_place_publishes_when_its_page_later_verifies(self):
        self.gate([row("man-new"), row("man-old")], {"man-new": BLOCKED, "man-old": OK})
        pub = self.gate([row("man-new"), row("man-old")], {"man-new": OK, "man-old": OK})
        self.assertEqual([x["id"] for x in pub], ["man-new", "man-old"])
        self.assertNotIn("kept_fetch_blocked", pub[0])
        rep = open("reports/manual_review.md").read()
        self.assertIn("None this run.", rep)
        self.assertNotIn("man-new", rep)
        self.assertEqual(json.load(open("logs/shelters_held.json"))["held"], [])
        self.assertEqual(json.load(open("logs/shelters_pending.json")), [])
    def test_unverifiable_row_is_held_and_the_guard_leaves_it_out(self):
        old = row("man-old", fetched_at="2026-10-30T00:00:00+00:00")
        closed = {"ok": False, "http": 200, "reason": "source now says closed/ended"}
        pub = self.gate([row("man-old"), row("man-new")], {"man-old": closed, "man-new": OK}, prev={"items": [old]})
        self.assertEqual([x["id"] for x in pub], ["man-new"])
        rep = open("reports/manual_review.md").read()
        self.assertIn("man-old", rep)
        self.assertIn("omitted this run: source now says closed/ended", rep)
        out, g = refresh_guard.guard("shelters", [old], pub, run_day=datetime.date.today().isoformat(), root=self.d)
        self.assertEqual([x["id"] for x in out], ["man-new"])
        self.assertEqual(g["not_restored"][0]["id"], "man-old")
    def test_loaded_page_and_old_hand_check_are_not_a_free_pass(self):
        old = row("man-old", fetched_at="2026-10-01T00:00:00+00:00", checked_on="2026-10-01")
        closed = {"ok": False, "http": 200, "reason": "source now says closed/ended"}
        pub = self.gate([row("man-old", checked_on="2026-10-01"), row("man-new")], {"man-old": closed, "man-new": OK}, prev={"items": [old]})
        self.assertEqual([x["id"] for x in pub], ["man-new"])
        pub = self.gate([row("man-old", checked_on="2026-10-01")], {"man-old": BLOCKED}, prev={"items": [dict(old, checked_on="2026-10-01")]})
        self.assertEqual([x["id"] for x in pub], ["man-old"])
        self.assertTrue(pub[0].get("kept_fetch_blocked"))

class Fresh(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(self.d + "/logs")
        self.git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.d, capture_output=True, check=True)
        self.git("init", "-q")
    def commit(self, name, text):
        open(os.path.join(self.d, name), "w").write(text)
        self.git("add", name)
        self.git("commit", "-qm", name)
    def go(self, layer):
        return subprocess.run([sys.executable, os.path.join(S, "verify_fresh.py"), layer], cwd=self.d, capture_output=True, text=True)
    def log(self, name, rows):
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        body = {"_run": {"fetched_at": now}}
        body.update(rows)
        json.dump(body, open(os.path.join(self.d, "logs", name), "w"))
        return now
    def test_new_blocked_is_dropped_and_the_confirmed_place_publishes(self):
        day = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        good = {"id": "man-old", "name": "Old Hostel", "fetched_at": "STAMP", "phone": "0161 111 1111", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}
        bad = {"id": "man-new", "name": "New Hostel", "grace": True, "kept_fetch_blocked": True, "source": "Manual (verified from source pages)",
               "checked_on": day, "fetched_at": day + "T00:00:00+00:00", "phone": "0161 000 0000", "address": "2 High St", "hours": "", "postcode": "M1 2AA"}
        stamp = self.log("shelters_recheck.json", {"man-old": {"ok": True, "fetched_at": "STAMP"}, "man-new": BLOCKED})
        good["fetched_at"] = stamp
        self.commit("shelters.js", js("SHELTERS", [dict(good)]))
        open(self.d + "/shelters.js", "w").write(js("SHELTERS", [good, bad]))
        # the recheck log's fetched_at must match the good row
        rc = json.load(open(self.d + "/logs/shelters_recheck.json"))
        rc["man-old"]["fetched_at"] = stamp
        json.dump(rc, open(self.d + "/logs/shelters_recheck.json", "w"))
        p = self.go("shelters")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        data = json.loads(open(self.d + "/shelters.js").read().split("=", 1)[1].strip().rstrip(";"))
        self.assertEqual([x["id"] for x in data["items"]], ["man-old"])
        rep = open(self.d + "/reports/manual_review.md").read()
        self.assertIn("man-new", rep)
        self.assertIn("was not published before", rep)
        self.assertNotIn("man-old", rep)
    def test_published_blocked_within_14_days_stays(self):
        day = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        item = {"id": "man-old", "name": "Old Hostel", "grace": True, "kept_fetch_blocked": True, "source": "Manual (verified from source pages)",
                "checked_on": day, "fetched_at": day + "T00:00:00+00:00", "phone": "0161 000 0000", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}
        pub = dict(item); pub.pop("grace"); pub.pop("kept_fetch_blocked")
        self.commit("shelters.js", js("SHELTERS", [pub]))
        open(self.d + "/shelters.js", "w").write(js("SHELTERS", [item]))
        self.log("shelters_recheck.json", {"man-old": BLOCKED})
        p = self.go("shelters")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("man-old", open(self.d + "/shelters.js").read())
        self.assertFalse(os.path.exists(self.d + "/reports/manual_review.md"))
    def test_only_bad_place_still_refuses(self):
        day = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        item = {"id": "man-new", "name": "New Hostel", "grace": True, "kept_fetch_blocked": True, "source": "Manual (verified from source pages)",
                "checked_on": day, "fetched_at": day + "T00:00:00+00:00", "phone": "0161 000 0000", "address": "1 High St", "hours": "", "postcode": "M1 1AA"}
        self.commit("shelters.js", js("SHELTERS", []))
        text = js("SHELTERS", [item])
        open(self.d + "/shelters.js", "w").write(text)
        self.log("shelters_recheck.json", {"man-new": BLOCKED})
        p = self.go("shelters")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("empty after holding", p.stdout)
        self.assertEqual(open(self.d + "/shelters.js").read(), text)
    def test_mass_shrink_still_refuses(self):
        stamp_items = [{"id": "s%d" % i, "fetched_at": "STAMP"} for i in range(5)]
        self.commit("shelters.js", js("SHELTERS", stamp_items))
        now = self.log("shelters_recheck.json", {})
        items = []
        rc = json.load(open(self.d + "/logs/shelters_recheck.json"))
        for i in range(5):
            items.append({"id": "s%d" % i, "fetched_at": now})
            rc["s%d" % i] = {"ok": i < 3, "http": 200, "reason": "confirmed this run" if i < 3 else "source now says closed/ended", "fetched_at": now}
        json.dump(rc, open(self.d + "/logs/shelters_recheck.json", "w"))
        text = js("SHELTERS", items)
        open(self.d + "/shelters.js", "w").write(text)
        p = self.go("shelters")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("20%", p.stdout)
        self.assertEqual(open(self.d + "/shelters.js").read(), text)
    def test_broken_file_and_missing_log_refuse(self):
        open(self.d + "/shelters.js", "w").write("this will not parse")
        self.log("shelters_recheck.json", {})
        p = self.go("shelters")
        self.assertEqual(p.returncode, 1)
        self.assertIn("will not parse", p.stdout)
        os.remove(self.d + "/logs/shelters_recheck.json")
        p = self.go("shelters")
        self.assertEqual(p.returncode, 1)
        self.assertIn("missing", p.stdout)
    def test_one_new_food_bank_is_held_and_the_run_continues(self):
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
        good = {"id": "fb-ok", "fetched_at": now}
        bad = {"id": "fb-bad", "fetched_at": now}
        self.commit("data.full.js", js("FB_DATA", [good]))
        open(self.d + "/data.full.js", "w").write(js("FB_DATA", [good, bad]))
        json.dump({"_run": {"fetched_at": now}, "fb-ok": {"ok": True, "fetched_at": now}, "fb-bad": {"ok": False, "http": 403}}, open(self.d + "/logs/foodbank_recheck.json", "w"))
        p = self.go("foodbanks")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        text = open(self.d + "/data.full.js").read()
        self.assertIn("fb-ok", text); self.assertNotIn("fb-bad", text)

class Guard(unittest.TestCase):
    def test_held_this_run_is_not_restored_and_yesterdays_list_is_not_a_freeze(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(d + "/logs")
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        held, other, gone = {"id": "man-held", "name": "Held"}, {"id": "man-stay", "name": "Stay"}, {"id": "man-gone", "name": "Gone"}
        json.dump({"run": today, "held": [{"id": "man-held", "name": "Held", "reason": "held this run: fetch blocked, not published before"}]}, open(d + "/logs/shelters_held.json", "w"))
        out, rep = refresh_guard.guard("shelters", [held, other, gone], [other], run_day=today, root=d)
        self.assertEqual([x["id"] for x in out], ["man-stay", "man-gone"])
        self.assertEqual(rep["not_restored"], [{"id": "man-held", "why": "held this run: fetch blocked, not published before"}])
        json.dump({"run": yesterday, "held": [{"id": "man-held", "name": "Held", "reason": "held this run: fetch blocked, not published before"}]}, open(d + "/logs/shelters_held.json", "w"))
        out, rep = refresh_guard.guard("shelters", [held, other], [other], run_day=today, root=d)
        self.assertEqual([x["id"] for x in out], ["man-stay", "man-held"])
        self.assertNotIn("not_restored", rep)

if __name__ == "__main__":
    unittest.main()
